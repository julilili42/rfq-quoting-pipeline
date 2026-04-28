"""Step execution context.

Anything a step might need that *isn't* part of its typed input lives
here: the working directory, the progress callback, helpers for
persisting intermediate state. Keeps step signatures clean — a step's
``run()`` method takes only the data it operates on, plus a ``ctx``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..output import save_json
from .progress import ProgressCallback, StepProgress, StepStatus, noop_progress


@dataclass
class StepContext:
    """Per-run context handed to every step."""

    work_dir: Path
    progress: ProgressCallback = field(default=noop_progress)

    def persist(self, filename: str, data: Any) -> Path:
        """Write a JSON snapshot of intermediate state to the work dir."""
        path = self.work_dir / filename
        save_json(data, path)
        return path

    def report(self, step_name: str, status: StepStatus, detail: str = "") -> None:
        """Emit a progress event."""
        self.progress(StepProgress(step_name=step_name, status=status, detail=detail))
