"""Tests for the SQLite-backed pipeline job queue.

Covers enqueue/claim/complete/fail semantics, retry budget behavior,
atomic claim (no double-dispatch), and CASCADE-on-review-delete.
"""
from __future__ import annotations

import pytest

from quoting.api.job_queue import JobQueue


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review-1")
    return "review-1"


@pytest.fixture
def queue(sqlite_repo) -> JobQueue:
    return JobQueue(sqlite_repo)


def test_enqueue_returns_positive_id(queue, review_id):
    job_id = queue.enqueue(review_id, "extract")
    assert job_id > 0


def test_enqueued_job_is_pending(queue, review_id):
    job_id = queue.enqueue(review_id, "extract")
    job = queue.get(job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.attempts == 0
    assert job.last_error is None
    assert job.claimed_at is None
    assert job.completed_at is None


def test_claim_next_returns_oldest_pending(queue, review_id):
    first = queue.enqueue(review_id, "extract")
    queue.enqueue(review_id, "match")

    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed.id == first
    assert claimed.step == "extract"
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.claimed_at is not None


def test_claim_next_returns_none_when_empty(queue):
    assert queue.claim_next() is None


def test_claim_next_does_not_return_running_jobs(queue, review_id):
    queue.enqueue(review_id, "extract")
    first = queue.claim_next()
    assert first is not None

    # Second claim_next should NOT return the same job — it's running.
    second = queue.claim_next()
    assert second is None


def test_claim_next_is_atomic(queue, review_id):
    """Two consecutive claims on the same pending job must not both succeed.

    SQLite serialises writes via the WAL, so calling claim_next twice in
    succession is the closest we get to simulating two workers without
    threading. The second call must see the row as already-running.
    """
    queue.enqueue(review_id, "extract")
    first = queue.claim_next()
    second = queue.claim_next()
    assert first is not None
    assert second is None


def test_complete_marks_job_completed(queue, review_id):
    queue.enqueue(review_id, "extract")
    job = queue.claim_next()
    assert job is not None
    queue.complete(job.id)

    updated = queue.get(job.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.last_error is None


def test_fail_with_retry_budget_returns_to_pending(queue, review_id):
    queue.enqueue(review_id, "extract", max_attempts=3)
    job = queue.claim_next()
    assert job is not None

    new_status = queue.fail(job.id, "transient LLM error")
    assert new_status == "pending"

    reloaded = queue.get(job.id)
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.attempts == 1
    assert reloaded.last_error == "transient LLM error"
    assert reloaded.claimed_at is None  # ready for re-claim


def test_fail_after_max_attempts_marks_failed(queue, review_id):
    queue.enqueue(review_id, "extract", max_attempts=2)

    # First attempt
    job = queue.claim_next()
    assert job is not None
    new_status = queue.fail(job.id, "first error")
    assert new_status == "pending"

    # Second (and final) attempt
    job = queue.claim_next()
    assert job is not None
    assert job.attempts == 2
    new_status = queue.fail(job.id, "second error")
    assert new_status == "failed"

    reloaded = queue.get(job.id)
    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.last_error == "second error"


def test_retry_then_success_clears_last_error(queue, review_id):
    queue.enqueue(review_id, "extract", max_attempts=3)
    job = queue.claim_next()
    assert job is not None
    queue.fail(job.id, "transient")

    job = queue.claim_next()
    assert job is not None
    queue.complete(job.id)

    reloaded = queue.get(job.id)
    assert reloaded is not None
    assert reloaded.status == "completed"
    assert reloaded.attempts == 2
    assert reloaded.last_error is None  # completion clears the stale error


def test_payload_round_trips(queue, review_id):
    job_id = queue.enqueue(
        review_id,
        "render",
        payload={"is_final": True, "filename": "Angebot.pdf"},
    )
    job = queue.get(job_id)
    assert job is not None
    assert job.payload == {"is_final": True, "filename": "Angebot.pdf"}


def test_list_for_review_returns_jobs_in_order(queue, review_id):
    a = queue.enqueue(review_id, "extract")
    b = queue.enqueue(review_id, "match")
    c = queue.enqueue(review_id, "price")

    jobs = queue.list_for_review(review_id)
    assert [j.id for j in jobs] == [a, b, c]
    assert [j.step for j in jobs] == ["extract", "match", "price"]


def test_list_for_review_isolates_reviews(queue, sqlite_repo, review_id):
    sqlite_repo.create_review("review-2")
    queue.enqueue(review_id, "extract")
    queue.enqueue("review-2", "extract")

    assert len(queue.list_for_review(review_id)) == 1
    assert len(queue.list_for_review("review-2")) == 1


def test_jobs_cascade_when_review_deleted(queue, sqlite_repo, review_id):
    queue.enqueue(review_id, "extract")
    queue.enqueue(review_id, "match")
    sqlite_repo.delete_review(review_id)

    assert queue.list_for_review(review_id) == []


def test_fail_on_unknown_job_is_safe(queue):
    """Job rows can vanish (CASCADE on review delete) mid-run.

    The worker shouldn't crash if it tries to mark such a ghost as failed.
    """
    new_status = queue.fail(99999, "stale")
    assert new_status == "failed"
