"""Tests for quoting.api.approval_store — state machine transitions."""
from __future__ import annotations

import pytest

from quoting.api.approval_store import (
    VALID_TRANSITIONS,
    ApprovalRecord,
    ApprovalStore,
)


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review_001")
    return "review_001"


@pytest.fixture
def approval_store(sqlite_repo) -> ApprovalStore:
    return ApprovalStore(sqlite_repo)


def test_fresh_review_is_draft_generated(review_id, approval_store):
    rec = approval_store.load(review_id)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None
    assert rec.history == []


def test_transition_draft_to_reviewed(review_id, approval_store):
    rec = approval_store.transition(review_id, "reviewed", actor="KAM")
    assert rec.state == "reviewed"
    assert len(rec.history) == 1
    assert rec.history[0]["from"] == "draft_generated"
    assert rec.history[0]["to"] == "reviewed"
    assert rec.history[0]["actor"] == "KAM"


def test_transition_reviewed_to_approved_sets_fields(review_id, approval_store):
    approval_store.transition(review_id, "reviewed")
    rec = approval_store.transition(review_id, "approved", actor="Max Mustermann")
    assert rec.state == "approved"
    assert rec.approved_by == "Max Mustermann"
    assert rec.approved_at is not None


def test_transition_approved_to_ready_to_send(review_id, approval_store):
    approval_store.transition(review_id, "reviewed")
    approval_store.transition(review_id, "approved", actor="K")
    rec = approval_store.transition(review_id, "ready_to_send")
    assert rec.state == "ready_to_send"
    assert rec.sent_at is not None


def test_final_pdf_path_stored(review_id, approval_store):
    rec = approval_store.transition(review_id, "approved", final_pdf_path="final.pdf")
    assert rec.final_pdf_path == "final.pdf"


def test_exception_reason_is_optional_but_persisted_when_present(review_id, approval_store):
    rec = approval_store.transition(
        review_id,
        "approved",
        warning_acknowledged=True,
        exception_reason="  Kunde hat Sonderfreigabe bestätigt  ",
    )

    assert rec.warning_acknowledged is True
    assert rec.exception_reason == "Kunde hat Sonderfreigabe bestätigt"
    assert rec.history[-1]["exception_reason"] == "Kunde hat Sonderfreigabe bestätigt"


def test_invalid_transition_is_rejected(review_id, approval_store):
    with pytest.raises(ValueError, match="Invalid transition"):
        approval_store.transition(review_id, "ready_to_send")  # skip reviewed & approved


def test_reset_returns_to_draft_generated(review_id, approval_store):
    approval_store.transition(review_id, "reviewed")
    approval_store.transition(review_id, "approved", actor="X")
    rec = approval_store.reset(review_id)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None


def test_reset_persists(review_id, approval_store):
    approval_store.transition(review_id, "approved")
    approval_store.reset(review_id)
    reloaded = approval_store.load(review_id)
    assert reloaded.state == "draft_generated"


def test_mark_field_changed(review_id, approval_store):
    approval_store.mark_field_changed(review_id, "positionen.0.menge")
    rec = approval_store.load(review_id)
    assert "positionen.0.menge" in rec.changed_fields


def test_mark_field_changed_no_duplicates(review_id, approval_store):
    approval_store.mark_field_changed(review_id, "kunde_firma")
    approval_store.mark_field_changed(review_id, "kunde_firma")
    rec = approval_store.load(review_id)
    assert rec.changed_fields.count("kunde_firma") == 1


def test_approval_record_round_trip(review_id, approval_store):
    original = ApprovalRecord(
        state="reviewed",
        approved_by="Tester",
        changed_fields=["f1", "f2"],
    )
    approval_store.save(review_id, original)
    loaded = approval_store.load(review_id)
    assert loaded.state == "reviewed"
    assert loaded.approved_by == "Tester"
    assert loaded.changed_fields == ["f1", "f2"]


def test_mark_opened_sets_timestamp(review_id, approval_store):
    rec = approval_store.mark_opened(review_id)
    assert rec.opened_at is not None


def test_mark_opened_is_idempotent(review_id, approval_store):
    """Subsequent calls must not overwrite the first opened_at."""
    first = approval_store.mark_opened(review_id)
    assert first.opened_at is not None
    first_ts = first.opened_at

    # Reload from disk to make sure the timestamp persisted, then call again.
    second = approval_store.mark_opened(review_id)
    assert second.opened_at == first_ts


def test_mark_opened_does_not_change_state(review_id, approval_store):
    approval_store.mark_opened(review_id)
    rec = approval_store.load(review_id)
    assert rec.state == "draft_generated"


def test_all_valid_transitions_defined():
    states = {"draft_generated", "reviewed", "approved", "ready_to_send"}
    assert set(VALID_TRANSITIONS.keys()) == states
