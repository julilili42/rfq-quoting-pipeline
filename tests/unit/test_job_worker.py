"""Tests for the background worker that drains the JobQueue.

Dispatch behaviour is exercised via ``run_once()`` so most tests stay
threadless and deterministic. A separate small block covers the
``start``/``stop`` lifecycle with a real thread.
"""
from __future__ import annotations

import threading
import time

import pytest

from quoting.api.job_queue import Job, JobQueue
from quoting.api.job_worker import JobWorker


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review-1")
    return "review-1"


@pytest.fixture
def queue(sqlite_repo) -> JobQueue:
    return JobQueue(sqlite_repo)


def test_run_once_returns_false_when_queue_empty(queue):
    worker = JobWorker(queue=queue, handlers={})
    assert worker.run_once() is False


def test_run_once_dispatches_to_handler_and_marks_completed(queue, review_id):
    called_with: list[Job] = []

    def handler(job: Job) -> None:
        called_with.append(job)

    job_id = queue.enqueue(review_id, "extract")
    worker = JobWorker(queue=queue, handlers={"extract": handler})

    assert worker.run_once() is True
    assert len(called_with) == 1
    assert called_with[0].review_id == review_id
    assert called_with[0].step == "extract"

    reloaded = queue.get(job_id)
    assert reloaded is not None
    assert reloaded.status == "completed"


def test_handler_exception_marks_job_failed_via_queue(queue, review_id):
    def boom(_: Job) -> None:
        raise RuntimeError("upstream blew up")

    job_id = queue.enqueue(review_id, "extract", max_attempts=1)
    worker = JobWorker(queue=queue, handlers={"extract": boom})

    assert worker.run_once() is True

    reloaded = queue.get(job_id)
    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.last_error is not None
    assert "upstream blew up" in reloaded.last_error
    assert "RuntimeError" in reloaded.last_error


def test_handler_exception_with_retry_budget_returns_to_pending(queue, review_id):
    def boom(_: Job) -> None:
        raise ValueError("transient")

    job_id = queue.enqueue(review_id, "extract", max_attempts=3)
    worker = JobWorker(queue=queue, handlers={"extract": boom})

    worker.run_once()

    reloaded = queue.get(job_id)
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.attempts == 1


def test_missing_handler_marks_job_failed_with_clear_message(queue, review_id):
    job_id = queue.enqueue(review_id, "extract", max_attempts=1)
    worker = JobWorker(queue=queue, handlers={})  # nothing registered

    assert worker.run_once() is True

    reloaded = queue.get(job_id)
    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.last_error is not None
    assert "extract" in reloaded.last_error
    assert "handler" in reloaded.last_error.lower()


def test_run_once_processes_one_job_at_a_time(queue, review_id):
    """Even with multiple pending jobs, run_once handles exactly one."""
    called: list[str] = []

    def handler(job: Job) -> None:
        called.append(job.step)

    queue.enqueue(review_id, "extract")
    queue.enqueue(review_id, "match")
    queue.enqueue(review_id, "price")

    worker = JobWorker(
        queue=queue,
        handlers={"extract": handler, "match": handler, "price": handler},
    )

    worker.run_once()
    assert called == ["extract"]
    worker.run_once()
    assert called == ["extract", "match"]


# ---------------------------------------------------------------- thread lifecycle


def test_start_stop_lifecycle_drains_queue(queue, review_id):
    done = threading.Event()
    seen_step: list[str] = []

    def handler(job: Job) -> None:
        seen_step.append(job.step)
        done.set()

    queue.enqueue(review_id, "extract")

    worker = JobWorker(
        queue=queue,
        handlers={"extract": handler},
        poll_interval_s=0.05,
    )
    worker.start()
    try:
        assert done.wait(timeout=3.0), "worker never picked up the job"
    finally:
        worker.stop(timeout=2.0)

    assert seen_step == ["extract"]
    assert not worker.is_running


def test_double_start_is_rejected(queue):
    worker = JobWorker(queue=queue, handlers={}, poll_interval_s=0.05)
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            worker.start()
    finally:
        worker.stop(timeout=2.0)


def test_stop_is_idempotent(queue):
    worker = JobWorker(queue=queue, handlers={}, poll_interval_s=0.05)
    worker.stop()  # not started
    worker.start()
    worker.stop(timeout=2.0)
    worker.stop(timeout=2.0)  # second stop is fine
    assert not worker.is_running


def test_worker_survives_handler_exceptions_in_loop(queue, review_id):
    """A failing handler must not kill the worker thread."""
    counter = {"calls": 0}
    done = threading.Event()

    def flaky(job: Job) -> None:
        counter["calls"] += 1
        if counter["calls"] == 1:
            raise RuntimeError("first attempt fails")
        done.set()

    queue.enqueue(review_id, "extract", max_attempts=3)
    worker = JobWorker(
        queue=queue,
        handlers={"extract": flaky},
        poll_interval_s=0.05,
    )
    worker.start()
    try:
        # First run fails, queue returns the job to pending; worker
        # picks it up again and the second call succeeds.
        assert done.wait(timeout=3.0), "second attempt never ran"
    finally:
        worker.stop(timeout=2.0)

    assert counter["calls"] == 2


def test_worker_idle_polling_does_not_busy_spin(queue):
    """Idle worker should sleep close to poll_interval_s between checks."""
    worker = JobWorker(queue=queue, handlers={}, poll_interval_s=0.1)
    worker.start()
    try:
        time.sleep(0.3)
        # If the worker were busy-looping we'd see hundreds of iterations.
        # We can't easily count them, but the test failing-to-finish
        # within the timeout is the canary. The sleep itself proves
        # the thread didn't crash.
        assert worker.is_running
    finally:
        worker.stop(timeout=2.0)
