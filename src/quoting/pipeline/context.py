"""Step execution context.

Anything a step might need that *isn't* part of its typed input lives
here: the working directory, the progress callback, helpers for
persisting intermediate state. Keeps step signatures clean — a step's
``run()`` method takes only the data it operates on, plus a ``ctx``.
"""
from __future__ import annotations

from collections.abc import Callable
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
    extra: dict = field(default_factory=dict)
    snapshot_sink: Callable[[str, Any], None] | None = None

    def persist(self, name: str, data: Any) -> Path:
        """Persist a JSON snapshot of intermediate state.

        ``name`` is a logical payload name (no extension). When a
        ``snapshot_sink`` is configured it receives the raw name; when
        not, the data is written to ``<work_dir>/<name>.json`` for ad-hoc
        runs and integration tests.
        """
        if self.snapshot_sink is not None:
            self.snapshot_sink(name, data)
            return self.work_dir / name
        path = self.work_dir / f"{name}.json"
        save_json(data, path)
        return path

    def report(
        self,
        step_name: str,
        status: StepStatus,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a progress event."""
        self.progress(
            StepProgress(
                step_name=step_name,
                status=status,
                detail=detail,
                metadata=metadata,
            ),
        )
