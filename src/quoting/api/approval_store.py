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
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

from quoting.api.container import get_app_container
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

ApprovalState = Literal[
    "draft_generated",
    "reviewed",
    "approved",
    "ready_to_send",
]


VALID_TRANSITIONS: dict[ApprovalState, set[ApprovalState]] = {
    "draft_generated": {"reviewed", "approved"},
    "reviewed":        {"approved", "draft_generated"},
    "approved":        {"ready_to_send", "reviewed"},
    "ready_to_send":   {"approved"},
}


@dataclass
class ApprovalRecord:
    state: ApprovalState = "draft_generated"
    approved_by: str | None = None
    approved_at: str | None = None
    opened_at: str | None = None
    sent_at: str | None = None
    changed_fields: list[str] = field(default_factory=list)
    final_pdf_path: str | None = None
    warning_acknowledged: bool = False
    exception_reason: str | None = None
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ApprovalRecord:
        if not isinstance(data, dict):
            return cls()
        raw_state = data.get("state", "draft_generated")
        if raw_state not in ("draft_generated", "reviewed", "approved", "ready_to_send"):
            raw_state = "draft_generated"
        return cls(
            state=raw_state,
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            opened_at=data.get("opened_at"),
            sent_at=data.get("sent_at"),
            changed_fields=list(data.get("changed_fields") or []),
            final_pdf_path=data.get("final_pdf_path"),
            warning_acknowledged=bool(data.get("warning_acknowledged", False)),
            exception_reason=data.get("exception_reason"),
            history=list(data.get("history") or []),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalStore:
    repo: SQLiteReviewRepository

    def load(self, review_id: str) -> ApprovalRecord:
        return ApprovalRecord.from_dict(self.repo.load_approval(review_id))

    def save(self, review_id: str, record: ApprovalRecord) -> None:
        self.repo.save_approval(review_id, record.to_dict())

    def transition(
        self,
        review_id: str,
        target: ApprovalState,
        *,
        actor: str | None = None,
        changed_fields: list[str] | None = None,
        final_pdf_path: str | None = None,
        warning_acknowledged: bool | None = None,
        exception_reason: str | None = None,
    ) -> ApprovalRecord:
        """Move the review to a new state, recording who/when in history."""
        record = self.load(review_id)

        if target != record.state and target not in VALID_TRANSITIONS.get(record.state, set()):
            raise ValueError(f"Invalid transition {record.state!r} → {target!r}")
        entry: dict = {"at": _now_iso(), "from": record.state, "to": target, "actor": actor}
        record.history.append(entry)

        record.state = target
        if target == "approved":
            record.approved_by = actor
            record.approved_at = _now_iso()
        elif target == "ready_to_send":
            record.sent_at = _now_iso()
        elif target == "reviewed":
            record.exception_reason = None
        if final_pdf_path is not None:
            record.final_pdf_path = final_pdf_path
        if warning_acknowledged is not None:
            record.warning_acknowledged = warning_acknowledged
        if exception_reason is not None:
            reason = exception_reason.strip()
            record.exception_reason = reason or None
            if reason:
                entry["exception_reason"] = reason
        if changed_fields is not None:
            record.changed_fields = list(changed_fields)

        self.save(review_id, record)
        return record

    def reset(self, review_id: str) -> ApprovalRecord:
        """Hard reset — used when the user wants to re-run the pipeline."""
        record = ApprovalRecord(state="draft_generated")
        self.save(review_id, record)
        return record

    def mark_field_changed(self, review_id: str, field_path: str) -> None:
        """Add a field to the changelog without changing state."""
        record = self.load(review_id)
        if field_path not in record.changed_fields:
            record.changed_fields.append(field_path)
            self.save(review_id, record)

    def mark_opened(self, review_id: str) -> ApprovalRecord:
        """Record the first time the Review-UI was opened for this review.

        Idempotent — subsequent calls don't overwrite the timestamp. Used by
        the Outlook plugin to distinguish "review ready, user hasn't looked
        yet" from "review opened, awaiting approval".
        """
        record = self.load(review_id)
        if record.opened_at is None:
            record.opened_at = _now_iso()
            self.save(review_id, record)
        return record


def default_approval_store() -> ApprovalStore:
    return ApprovalStore(get_app_container().review_repo())


def load_approval(review_id: str) -> ApprovalRecord:
    return default_approval_store().load(review_id)


def save_approval(review_id: str, record: ApprovalRecord) -> None:
    default_approval_store().save(review_id, record)


def transition(
    review_id: str,
    target: ApprovalState,
    *,
    actor: str | None = None,
    changed_fields: list[str] | None = None,
    final_pdf_path: str | None = None,
    warning_acknowledged: bool | None = None,
    exception_reason: str | None = None,
) -> ApprovalRecord:
    return default_approval_store().transition(
        review_id,
        target,
        actor=actor,
        changed_fields=changed_fields,
        final_pdf_path=final_pdf_path,
        warning_acknowledged=warning_acknowledged,
        exception_reason=exception_reason,
    )


def reset_approval(review_id: str) -> ApprovalRecord:
    return default_approval_store().reset(review_id)


def mark_field_changed(review_id: str, field_path: str) -> None:
    default_approval_store().mark_field_changed(review_id, field_path)
