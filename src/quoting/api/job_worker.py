"""Background worker that drains the SQLite job queue.

Why
---
:class:`~quoting.api.job_queue.JobQueue` only provides durable storage
and atomic claim semantics. Something needs to actually pull jobs off
the queue and run them. That's this module.

Concurrency model
-----------------
A single worker thread polls every ``poll_interval_s`` seconds. One
thread is enough because:

- Pipeline steps for the same review must run in sequence (step N+1
  depends on step N's output), so per-review parallelism would deadlock
  on itself.
- Cross-review parallelism is limited by LLM rate limits and SQLite
  write contention anyway.
- It keeps the worker easy to reason about and easy to shut down.

If we ever need throughput, the right move is one ``JobWorker``
instance per dedicated SQLite connection — not one thread juggling many
in-flight jobs.

Handlers
--------
A handler is ``Callable[[Job], None]`` keyed by step name. The contract:

- Return normally on success — the worker marks the job ``completed``.
- Raise any exception on failure — the worker captures the message and
  hands it to :meth:`JobQueue.fail`, which decides whether to requeue
  or mark ``failed`` based on the retry budget.
- Handlers are responsible for their own idempotency. The worker may
  call the same handler again (with the same ``review_id``) after a
  retry — the handler must cope (typically by skipping when the
  expected output already exists in the review's payloads).
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from quoting.api.job_queue import Job, JobQueue
from quoting.core import get_logger

log = get_logger()

HandlerFn = Callable[[Job], None]


@dataclass
class JobWorker:
    queue: JobQueue
    handlers: dict[str, HandlerFn]
    poll_interval_s: float = 1.0
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("JobWorker is already running")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="JobWorker", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait for the current loop iteration.

        Does NOT interrupt a running handler — those finish to completion
        (or raise, which the worker catches). ``timeout`` bounds how long
        we'll wait for the thread to exit; long-running steps may exceed
        it, in which case the thread keeps running daemonised and the
        process exits on its own.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------------------------------------------------------------- dispatch
    def run_once(self) -> bool:
        """Process one pending job, if any.

        Returns ``True`` when a job was claimed and dispatched (regardless
        of whether the handler succeeded or failed), ``False`` when the
        queue was empty. Exposed for tests so the dispatch path can be
        exercised without spinning up a thread.
        """
        job = self.queue.claim_next()
        if job is None:
            return False
        self._dispatch(job)
        return True

    def _dispatch(self, job: Job) -> None:
        handler = self.handlers.get(job.step)
        if handler is None:
            message = f"No handler registered for step {job.step!r}"
            log.error("Job %d (%s): %s", job.id, job.step, message)
            self.queue.fail(job.id, message)
            return
        try:
            handler(job)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            log.exception(
                "Job %d (%s/%s) handler raised", job.id, job.review_id, job.step
            )
            self.queue.fail(job.id, message)
            return
        self.queue.complete(job.id)
        log.info(
            "Job %d (%s/%s) completed in %d attempt(s)",
            job.id, job.review_id, job.step, job.attempts,
        )

    # -------------------------------------------------------------------- loop
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.run_once()
            except Exception:
                # claim_next / DB locked / etc. — don't take the thread
                # down with us; just back off and try again.
                log.exception("JobWorker iteration failed; backing off")
                processed = False
            if not processed:
                # Sleep here, but break out early when stop() is signalled.
                self._stop.wait(timeout=self.poll_interval_s)
