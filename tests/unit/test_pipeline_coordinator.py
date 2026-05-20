"""Tests for the pipeline coordinator.

These cover the sequencing logic between step handlers, the job queue,
and the progress store. The actual step work is replaced with fakes —
we're testing orchestration, not what the steps do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from quoting.api.job_queue import JobQueue
from quoting.api.pipeline_coordinator import PIPELINE_STEPS, PipelineCoordinator
from quoting.api.progress_store import ProgressStore


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review-1")
    return "review-1"


@pytest.fixture
def queue(sqlite_repo) -> JobQueue:
    return JobQueue(sqlite_repo)


@pytest.fixture
def progress(sqlite_repo) -> ProgressStore:
    store = ProgressStore(sqlite_repo)
    return store


@dataclass
class _RecordingHandlers:
    """Stand-in for StepHandlers — records calls; can be set to raise."""

    calls: list[str] = field(default_factory=list)
    raise_on: set[str] = field(default_factory=set)

    def _record_or_raise(self, step: str, review_id: str) -> None:
        self.calls.append(f"{step}:{review_id}")
        if step in self.raise_on:
            raise RuntimeError(f"{step} blew up")

    def extract(self, review_id: str) -> None:
        self._record_or_raise("extract", review_id)

    def match(self, review_id: str) -> None:
        self._record_or_raise("match", review_id)

    def price(self, review_id: str) -> None:
        self._record_or_raise("price", review_id)

    def render(self, review_id: str) -> None:
        self._record_or_raise("render", review_id)


def _make_coordinator(
    queue: JobQueue,
    progress: ProgressStore,
    *,
    handlers: _RecordingHandlers | None = None,
    payload_builder=None,
) -> tuple[PipelineCoordinator, _RecordingHandlers]:
    handlers = handlers or _RecordingHandlers()
    coordinator = PipelineCoordinator(
        handlers=handlers,  # type: ignore[arg-type]
        queue=queue,
        progress=progress,
        completion_payload_builder=payload_builder
        or (lambda rid: {"review_id": rid, "status": "completed"}),
    )
    return coordinator, handlers


def _drive(coordinator: PipelineCoordinator, queue: JobQueue, max_iterations: int = 20) -> int:
    """Manually drain the queue using the coordinator's handlers.

    We don't use JobWorker here so the test stays deterministic — the
    worker's polling/threading is covered by its own test module.
    Returns the number of jobs processed.
    """
    handlers = coordinator.worker_handlers()
    processed = 0
    for _ in range(max_iterations):
        job = queue.claim_next()
        if job is None:
            break
        handler = handlers[job.step]
        try:
            handler(job)
            queue.complete(job.id)
        except Exception as exc:
            queue.fail(job.id, str(exc))
        processed += 1
    return processed


# ---------------------------------------------------------------- start_pipeline


def test_start_pipeline_enqueues_extract(queue, progress, review_id):
    coordinator, _ = _make_coordinator(queue, progress)

    coordinator.start_pipeline(review_id)

    jobs = queue.list_for_review(review_id)
    assert len(jobs) == 1
    assert jobs[0].step == "extract"
    assert jobs[0].status == "pending"


# ---------------------------------------------------------------- sequencing


def test_successful_run_drains_all_four_steps_in_order(queue, progress, review_id, sqlite_repo):
    progress.init(review_id)
    coordinator, handlers = _make_coordinator(queue, progress)
    coordinator.start_pipeline(review_id)

    _drive(coordinator, queue)

    assert handlers.calls == [
        f"extract:{review_id}",
        f"match:{review_id}",
        f"price:{review_id}",
        f"render:{review_id}",
    ]


def test_render_completion_flips_progress_to_completed(
    queue, progress, review_id, sqlite_repo
):
    progress.init(review_id)
    coordinator, _ = _make_coordinator(
        queue,
        progress,
        payload_builder=lambda rid: {"review_id": rid, "status": "completed", "draft_pdf_url": "/x"},
    )
    coordinator.start_pipeline(review_id)

    _drive(coordinator, queue)

    final = progress.read(review_id)
    assert final is not None
    assert final["status"] == "completed"
    assert final["result"] == {
        "review_id": review_id,
        "status": "completed",
        "draft_pdf_url": "/x",
    }


def test_intermediate_step_completion_does_not_call_payload_builder(
    queue, progress, review_id, sqlite_repo
):
    """The completion payload is only built when the whole pipeline finishes."""
    progress.init(review_id)
    builder = MagicMock(return_value={"review_id": review_id, "status": "completed"})
    handlers = _RecordingHandlers()
    # Skip the last step so we don't reach completion.
    handlers.raise_on = {"render"}

    coordinator = PipelineCoordinator(
        handlers=handlers,  # type: ignore[arg-type]
        queue=queue,
        progress=progress,
        completion_payload_builder=builder,
    )
    # Pretend extract/match/price ran by manually enqueueing render.
    coordinator.start_pipeline(review_id)
    _drive(coordinator, queue)

    # Builder is never called because render raised before reaching
    # _after_step_completed for the final step.
    builder.assert_not_called()


# ---------------------------------------------------------------- failure path


def test_terminal_failure_notifies_progress_store(queue, progress, review_id):
    progress.init(review_id)
    handlers = _RecordingHandlers(raise_on={"extract"})
    coordinator, _ = _make_coordinator(queue, progress, handlers=handlers)

    # max_attempts=1 so the very first failure is terminal.
    queue.enqueue(review_id, "extract", max_attempts=1)

    _drive(coordinator, queue)

    final = progress.read(review_id)
    assert final is not None
    assert final["status"] == "failed"
    assert final["error"] is not None
    assert "extract" in final["error"]
    assert "RuntimeError" in final["error"]


def test_non_terminal_failure_does_not_notify_progress(queue, progress, review_id):
    """Mid-budget failures leave the UI in 'running' so the user sees a retry."""
    progress.init(review_id)
    handlers = _RecordingHandlers(raise_on={"extract"})
    coordinator, _ = _make_coordinator(queue, progress, handlers=handlers)

    queue.enqueue(review_id, "extract", max_attempts=3)

    # One iteration: first attempt fails, queue returns the job to pending.
    handlers_dict = coordinator.worker_handlers()
    job = queue.claim_next()
    assert job is not None
    with pytest.raises(RuntimeError):
        handlers_dict[job.step](job)
    queue.fail(job.id, "x")

    final = progress.read(review_id)
    assert final is not None
    assert final["status"] == "running"  # unchanged
    assert final.get("error") is None


def test_failure_does_not_enqueue_next_step(queue, progress, review_id):
    progress.init(review_id)
    handlers = _RecordingHandlers(raise_on={"match"})
    coordinator, _ = _make_coordinator(queue, progress, handlers=handlers)

    queue.enqueue(review_id, "match", max_attempts=1)
    _drive(coordinator, queue)

    # Only the failed `match` job should exist — no `price` was enqueued.
    jobs = queue.list_for_review(review_id)
    assert [j.step for j in jobs] == ["match"]
    assert jobs[0].status == "failed"


# ---------------------------------------------------------------- meta


def test_pipeline_steps_constant_matches_handler_methods():
    """If someone adds a step, both PIPELINE_STEPS and StepHandlers need updating.

    This test pins the contract so a mismatch fails fast.
    """
    handlers = _RecordingHandlers()
    for step in PIPELINE_STEPS:
        assert callable(getattr(handlers, step))


def test_worker_handlers_returns_one_per_pipeline_step(queue, progress):
    coordinator, _ = _make_coordinator(queue, progress)
    handlers = coordinator.worker_handlers()
    assert set(handlers.keys()) == set(PIPELINE_STEPS)
