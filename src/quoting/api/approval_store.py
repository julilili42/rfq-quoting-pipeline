"""Per-review approval state machine.

States
------
- ``draft_generated`` — pipeline produced a first PDF (initial state)
- ``reviewed``        — user has viewed and adjusted at least one field
- ``approved``        — user explicitly clicked "Approve". PDF is rebuilt
                        without the red AI-warning banner.
- ``ready_to_send``   — final PDF has been delivered to Outlook for sending

Transitions are linear; you can move backwards by resetting (which clears
the approval and restarts at ``draft_generated``).

Each state change is persisted next to the review folder so the dashboard
and Outlook plugin can read it without any in-memory coupling.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ApprovalState = Literal[
    "draft_generated",
    "reviewed",
    "approved",
    "ready_to_send",
]

VALID_TRANSITIONS: dict[ApprovalState, set[ApprovalState]] = {
    "draft_generated": {"reviewed", "approved"},
    "reviewed": {"approved", "draft_generated"},
    "approved": {"ready_to_send", "reviewed"},
    "ready_to_send": {"approved"},
}


@dataclass
class ApprovalRecord:
    state: ApprovalState = "draft_generated"
    approved_by: str | None = None
    approved_at: str | None = None
    sent_at: str | None = None
    changed_fields: list[str] = field(default_factory=list)
    final_pdf_path: str | None = None
    warning_acknowledged: bool = False
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ApprovalRecord":
        if not isinstance(data, dict):
            return cls()
        return cls(
            state=data.get("state", "draft_generated"),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            sent_at=data.get("sent_at"),
            changed_fields=list(data.get("changed_fields") or []),
            final_pdf_path=data.get("final_pdf_path"),
            warning_acknowledged=bool(data.get("warning_acknowledged", False)),
            history=list(data.get("history") or []),
        )


def approval_path(review_dir: Path) -> Path:
    return review_dir / "approval.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_approval(review_dir: Path) -> ApprovalRecord:
    path = approval_path(review_dir)
    if not path.exists():
        return ApprovalRecord()
    try:
        return ApprovalRecord.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except Exception:
        return ApprovalRecord()


def save_approval(review_dir: Path, record: ApprovalRecord) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    path = approval_path(review_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def transition(
    review_dir: Path,
    target: ApprovalState,
    *,
    actor: str | None = None,
    changed_fields: list[str] | None = None,
    final_pdf_path: str | None = None,
    warning_acknowledged: bool | None = None,
) -> ApprovalRecord:
    """Move the review to a new state, recording who/when in history."""
    record = load_approval(review_dir)

    if target not in VALID_TRANSITIONS.get(record.state, set()) and target != record.state:
        # Allow lateral transitions during prototyping but log them.
        record.history.append({
            "at": _now_iso(),
            "from": record.state,
            "to": target,
            "actor": actor,
            "warning": "non-standard transition",
        })
    else:
        record.history.append({
            "at": _now_iso(),
            "from": record.state,
            "to": target,
            "actor": actor,
        })

    record.state = target

    if target == "approved":
        record.approved_by = actor
        record.approved_at = _now_iso()
    if target == "ready_to_send":
        record.sent_at = _now_iso()
    if final_pdf_path is not None:
        record.final_pdf_path = final_pdf_path
    if warning_acknowledged is not None:
        record.warning_acknowledged = warning_acknowledged
    if changed_fields is not None:
        record.changed_fields = list(changed_fields)

    save_approval(review_dir, record)
    return record


def reset_approval(review_dir: Path) -> ApprovalRecord:
    """Hard reset — used when the user wants to re-run the pipeline."""
    record = ApprovalRecord(state="draft_generated")
    save_approval(review_dir, record)
    return record


def mark_field_changed(review_dir: Path, field_path: str) -> None:
    """Add a field to the changelog without changing state."""
    record = load_approval(review_dir)
    if field_path not in record.changed_fields:
        record.changed_fields.append(field_path)
    save_approval(review_dir, record)
