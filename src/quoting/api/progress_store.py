from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from quoting.api.container import get_app_container
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

_log = logging.getLogger("quoting.progress_store")

PIPELINE_STEPS = [
    "Mail vorbereiten",
    "Extraktion",
    "Matching",
    "Preisberechnung",
    "PDF-Rendering",
]

STEP_STATUS_MAP = {
    "started": "running",
    "completed": "completed",
    "failed": "failed",
    "skipped": "skipped",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressStore:
    def __init__(self, repo: SQLiteReviewRepository):
        self.repo = repo

    def init(self, review_id: str) -> dict[str, Any]:
        now = _now_iso()
        data: dict[str, Any] = {
            "review_id": review_id,
            "status": "running",
            "current_step": "Mail vorbereiten",
            "current_detail": "Review wird vorbereitet",
            "progress_percent": 0,
            "created_at": now,
            "updated_at": now,
            "steps": [
                {
                    "name": step_name,
                    "status": "running" if step_name == "Mail vorbereiten" else "pending",
                    "detail": "Review wird vorbereitet" if step_name == "Mail vorbereiten" else "",
                    "updated_at": now if step_name == "Mail vorbereiten" else None,
                    "started_at": now if step_name == "Mail vorbereiten" else None,
                    "completed_at": None,
                }
                for step_name in PIPELINE_STEPS
            ],
            "result": None,
            "error": None,
        }
        self.write(review_id, data)
        return data

    def read(self, review_id: str) -> dict[str, Any] | None:
        return self.repo.load_progress(review_id)

    def write(self, review_id: str, data: dict[str, Any]) -> None:
        self.repo.save_progress(review_id, data)

    def update_step(
        self,
        review_id: str,
        step_name: str,
        status: str,
        detail: str = "",
    ) -> None:
        data = self.read(review_id)
        if data is None:
            return

        mapped_status = STEP_STATUS_MAP.get(status, status)
        now = _now_iso()

        steps = data.get("steps", [])

        for step in steps:
            if step.get("name") != step_name:
                continue

            step["status"] = mapped_status
            step["detail"] = detail
            step["updated_at"] = now
            if mapped_status == "running" and not step.get("started_at"):
                step["started_at"] = now
            if mapped_status in {"completed", "skipped"}:
                if not step.get("started_at"):
                    step["started_at"] = now
                step["completed_at"] = now
            break

        completed_count = sum(
            1 for step in steps if step.get("status") in {"completed", "skipped"}
        )
        total_count = len(steps) or 1

        data["progress_percent"] = int((completed_count / total_count) * 100)
        data["updated_at"] = now

        if mapped_status == "running":
            data["status"] = "running"
            data["current_step"] = step_name
            data["current_detail"] = detail
            data["error"] = None

        elif mapped_status == "completed":
            running_steps = [
                step for step in steps if step.get("status") == "running"
            ]
            next_pending = next(
                (step for step in steps if step.get("status") == "pending"),
                None,
            )

            if running_steps:
                data["current_step"] = running_steps[0].get("name", step_name)
                data["current_detail"] = running_steps[0].get("detail", "")
            elif next_pending:
                data["current_step"] = next_pending.get("name", step_name)
                data["current_detail"] = next_pending.get("detail", "")
            else:
                data["current_step"] = step_name
                data["current_detail"] = detail

        elif mapped_status == "failed":
            data["status"] = "failed"
            data["current_step"] = step_name
            data["current_detail"] = detail
            data["error"] = detail or f"Step failed: {step_name}"

        self.write(review_id, data)

    def complete(self, review_id: str, result: dict[str, Any]) -> None:
        data = self.read(review_id)
        if data is None:
            _log.warning("complete_progress: progress payload missing for %s — creating synthetic record", review_id)
            data = {"review_id": review_id, "status": "running", "steps": [], "result": None, "error": None}

        now = _now_iso()

        for step in data.get("steps", []):
            if step.get("status") in {"pending", "running"}:
                step["status"] = "completed"
                step["updated_at"] = now
                if not step.get("started_at"):
                    step["started_at"] = now
                step["completed_at"] = now

        data["status"] = "completed"
        data["current_step"] = "Review bereit"
        data["current_detail"] = "Pipeline abgeschlossen"
        data["progress_percent"] = 100
        data["result"] = result
        data["error"] = None
        data["updated_at"] = now

        self.write(review_id, data)

    def fail(self, review_id: str, error: str) -> None:
        data = self.read(review_id)
        if data is None:
            _log.warning("fail_progress: progress payload missing for %s — creating synthetic record", review_id)
            data = {"review_id": review_id, "status": "running", "steps": [], "result": None, "error": None}

        now = _now_iso()

        for step in data.get("steps", []):
            if step.get("status") == "running":
                step["status"] = "failed"
                step["detail"] = error
                step["updated_at"] = now
                step["completed_at"] = now
                break

        data["status"] = "failed"
        data["current_detail"] = error
        data["error"] = error
        data["updated_at"] = now

        self.write(review_id, data)


def default_progress_store() -> ProgressStore:
    return ProgressStore(get_app_container().review_repo())


def init_progress(review_id: str) -> dict[str, Any]:
    return default_progress_store().init(review_id)


def read_progress(review_id: str) -> dict[str, Any] | None:
    return default_progress_store().read(review_id)


def write_progress(review_id: str, data: dict[str, Any]) -> None:
    default_progress_store().write(review_id, data)


def update_step(
    review_id: str,
    step_name: str,
    status: str,
    detail: str = "",
) -> None:
    default_progress_store().update_step(review_id, step_name, status, detail)


def complete_progress(review_id: str, result: dict[str, Any]) -> None:
    default_progress_store().complete(review_id, result)


def fail_progress(review_id: str, error: str) -> None:
    default_progress_store().fail(review_id, error)
