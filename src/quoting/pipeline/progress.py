"""Progress reporting for pipeline runs.

A pipeline that doesn't tell anyone what it's doing is a black box. Each
step calls ``ctx.report(...)`` at start and finish; callers register a
``ProgressCallback`` to translate those events into UI updates, log
lines, or SSE messages.

Status values are intentionally coarse — ``started`` / ``completed`` /
``failed`` / ``skipped``. Anything finer lives in the free-form ``detail``
string so step authors don't have to coordinate vocabularies with the UI.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

StepStatus = Literal["started", "completed", "failed", "skipped"]


@dataclass(frozen=True)
class StepProgress:
    """One event in a step's lifecycle."""

    step_name: str
    status: StepStatus
    detail: str = ""
    metadata: dict[str, Any] | None = None


ProgressCallback = Callable[[StepProgress], None]


def noop_progress(_: StepProgress) -> None:
    """Default callback — discards all events."""
    return None
