"""Persistent job queue backed by SQLite.

Why
---
The quoting pipeline used to run synchronously inside a FastAPI
``BackgroundTask``. That meant: a server restart dropped in-flight
runs, a failure in step 3 threw away steps 1-2 of work, and there was
no way to retry just one step. This module replaces that with a
durable per-step queue.

Each pipeline step (``extract``, ``match``, ``price``, ``render``) is
modelled as a discrete job row. A worker (see :mod:`job_worker` —
Stage 1b) claims rows atomically and dispatches to a step handler.
On success the handler enqueues the next step; on failure the job
either returns to ``pending`` (within the retry budget) or is marked
``failed``.

States
------

- ``pending``    — waiting to be claimed
- ``running``    — claimed by a worker, in progress
- ``completed``  — finished successfully
- ``failed``     — exceeded ``max_attempts``; manual intervention needed

The ``attempts`` counter increments on every claim, so a successful
run after 2 failures will show ``attempts = 3, status = completed``.

Concurrency
-----------
``claim_next`` uses ``UPDATE ... RETURNING`` against the smallest-id
``pending`` row, which SQLite executes as a single statement under
the write lock — two workers cannot claim the same job.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from quoting.reviews.sqlite_repository import SQLiteReviewRepository

JobStatus = Literal["pending", "running", "completed", "failed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Job:
    id: int
    review_id: str
    step: str
    status: JobStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    payload: dict[str, Any] | None
    created_at: str
    claimed_at: str | None
    completed_at: str | None


def _row_to_job(row: Any) -> Job:
    payload_raw = row["payload_json"]
    payload = json.loads(payload_raw) if payload_raw else None
    return Job(
        id=int(row["id"]),
        review_id=str(row["review_id"]),
        step=str(row["step"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        last_error=row["last_error"],
        payload=payload,
        created_at=str(row["created_at"]),
        claimed_at=row["claimed_at"],
        completed_at=row["completed_at"],
    )


@dataclass
class JobQueue:
    repo: SQLiteReviewRepository

    def enqueue(
        self,
        review_id: str,
        step: str,
        *,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> int:
        """Add a new pending job and return its id."""
        with self.repo.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jobs
                    (review_id, step, status, max_attempts, payload_json, created_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (
                    review_id,
                    step,
                    max_attempts,
                    json.dumps(payload) if payload is not None else None,
                    _now_iso(),
                ),
            )
            return int(cur.lastrowid or 0)

    def claim_next(self) -> Job | None:
        """Atomically claim the oldest pending job, transitioning it to running.

        Returns ``None`` when the queue is empty. The ``attempts`` counter
        is bumped here, so :meth:`fail` only needs to compare against
        ``max_attempts``.
        """
        with self.repo.connect() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    claimed_at = ?,
                    attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE status = 'pending'
                    ORDER BY id
                    LIMIT 1
                )
                RETURNING *
                """,
                (_now_iso(),),
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def complete(self, job_id: int) -> None:
        with self.repo.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed',
                    completed_at = ?,
                    last_error = NULL
                WHERE id = ?
                """,
                (_now_iso(), job_id),
            )

    def fail(self, job_id: int, error: str) -> JobStatus:
        """Record a failure. Returns the new status: ``pending`` if there
        are retries left, otherwise ``failed``.
        """
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                # Job was deleted out from under us (review cascade-deleted
                # mid-run). Nothing to update.
                return "failed"
            target: JobStatus = (
                "failed" if row["attempts"] >= row["max_attempts"] else "pending"
            )
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    last_error = ?,
                    claimed_at = NULL
                WHERE id = ?
                """,
                (target, error, job_id),
            )
            return target

    def get(self, job_id: int) -> Job | None:
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def list_for_review(self, review_id: str) -> list[Job]:
        with self.repo.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE review_id = ? ORDER BY id",
                (review_id,),
            ).fetchall()
        return [_row_to_job(row) for row in rows]
