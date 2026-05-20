"""Coordinator that drives a review through the four pipeline steps.

Stage 3 of the job-queue refactor. This is the only place that knows
the *order* of the pipeline steps and what to do at the boundaries
(enqueue the next one, mark the run complete, notify the UI on
terminal failure).

The split of concerns from earlier stages:

- :class:`~quoting.api.job_queue.JobQueue` — durable storage, atomic
  claim, retry budget.
- :class:`~quoting.api.job_worker.JobWorker` — polling loop, generic
  dispatch by step name, exception capture.
- :class:`~quoting.api.step_handlers.StepHandlers` — idempotent work
  for a single step.
- :class:`PipelineCoordinator` (this module) — sequence the steps,
  bridge the success/failure events back to ``ProgressStore``.

The coordinator owns the wrapping. The worker calls
``coordinator.worker_handlers()`` and stays unaware of the pipeline
shape — it just sees a dict of step names to callables.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from quoting.api.job_queue import JobQueue
from quoting.api.job_worker import HandlerFn
from quoting.api.progress_store import ProgressStore
from quoting.api.step_handlers import StepHandlers
from quoting.core import get_logger

log = get_logger()

# Canonical step order. The coordinator enqueues step N+1 only after
# step N completes; on completion of the last step it notifies the
# progress store.
PIPELINE_STEPS: tuple[str, ...] = ("extract", "match", "price", "render")

CompletionPayloadBuilder = Callable[[str], dict]


@dataclass
class PipelineCoordinator:
    handlers: StepHandlers
    queue: JobQueue
    progress: ProgressStore
    completion_payload_builder: CompletionPayloadBuilder

    # ---------------------------------------------------------------- entry points
    def start_pipeline(self, review_id: str) -> int:
        """Kick off a fresh pipeline run by enqueueing the first step."""
        return self.queue.enqueue(review_id, PIPELINE_STEPS[0])

    def worker_handlers(self) -> dict[str, HandlerFn]:
        """Return the handler dict the :class:`JobWorker` should be configured with."""
        return {step: self._wrap(step) for step in PIPELINE_STEPS}

    # ----------------------------------------------------------------- internals
    def _wrap(self, step: str) -> HandlerFn:
        """Return a job-level handler for ``step`` that handles the boundaries.

        Success → enqueue next step (or mark run complete on the last one).
        Exception → check whether this attempt was terminal; if so, also
        flag the pipeline as failed in ``ProgressStore``. The exception
        is re-raised so the worker's normal capture path still records
        the error on the job row.
        """
        step_method = getattr(self.handlers, step)

        def handler(job) -> None:
            try:
                step_method(job.review_id)
            except Exception as exc:
                # The worker bumped attempts on claim, so `attempts ==
                # max_attempts` means this run is the last try. Match
                # the queue's own check (see JobQueue.fail).
                if job.attempts >= job.max_attempts:
                    self.progress.fail(
                        job.review_id,
                        f"{step}: {type(exc).__name__}: {exc}",
                    )
                raise
            self._after_step_completed(job.review_id, step)

        return handler

    def _after_step_completed(self, review_id: str, completed_step: str) -> None:
        try:
            idx = PIPELINE_STEPS.index(completed_step)
        except ValueError:
            log.warning(
                "PipelineCoordinator got completion for unknown step %r — ignoring",
                completed_step,
            )
            return

        if idx + 1 < len(PIPELINE_STEPS):
            next_step = PIPELINE_STEPS[idx + 1]
            self.queue.enqueue(review_id, next_step)
            return

        # Final step done → flip the progress payload to completed.
        try:
            payload = self.completion_payload_builder(review_id)
        except Exception:
            log.exception(
                "completion_payload_builder failed for %s — completing without payload",
                review_id,
            )
            payload = {"review_id": review_id, "status": "completed"}
        self.progress.complete(review_id, payload)
