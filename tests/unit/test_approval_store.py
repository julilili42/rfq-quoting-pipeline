"""Tests for quoting.api.approval_store — state machine transitions."""
from __future__ import annotations

import pytest

from quoting.api.approval_store import (
    VALID_TRANSITIONS,
    ApprovalRecord,
    load_approval,
    mark_field_changed,
    reset_approval,
    save_approval,
    transition,
)


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review_001")
    return "review_001"


def test_fresh_review_is_draft_generated(review_id):
    rec = load_approval(review_id)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None
    assert rec.history == []


def test_transition_draft_to_reviewed(review_id):
    rec = transition(review_id, "reviewed", actor="KAM")
    assert rec.state == "reviewed"
    assert len(rec.history) == 1
    assert rec.history[0]["from"] == "draft_generated"
    assert rec.history[0]["to"] == "reviewed"
    assert rec.history[0]["actor"] == "KAM"


def test_transition_reviewed_to_approved_sets_fields(review_id):
    transition(review_id, "reviewed")
    rec = transition(review_id, "approved", actor="Max Mustermann")
    assert rec.state == "approved"
    assert rec.approved_by == "Max Mustermann"
    assert rec.approved_at is not None


def test_transition_approved_to_ready_to_send(review_id):
    transition(review_id, "reviewed")
    transition(review_id, "approved", actor="K")
    rec = transition(review_id, "ready_to_send")
    assert rec.state == "ready_to_send"
    assert rec.sent_at is not None


def test_final_pdf_path_stored(review_id):
    rec = transition(review_id, "approved", final_pdf_path="final.pdf")
    assert rec.final_pdf_path == "final.pdf"


def test_exception_reason_is_optional_but_persisted_when_present(review_id):
    rec = transition(
        review_id,
        "approved",
        warning_acknowledged=True,
        exception_reason="  Kunde hat Sonderfreigabe bestätigt  ",
    )

    assert rec.warning_acknowledged is True
    assert rec.exception_reason == "Kunde hat Sonderfreigabe bestätigt"
    assert rec.history[-1]["exception_reason"] == "Kunde hat Sonderfreigabe bestätigt"


def test_invalid_transition_is_rejected(review_id):
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(review_id, "ready_to_send")  # skip reviewed & approved


def test_reset_returns_to_draft_generated(review_id):
    transition(review_id, "reviewed")
    transition(review_id, "approved", actor="X")
    rec = reset_approval(review_id)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None


def test_reset_persists(review_id):
    transition(review_id, "approved")
    reset_approval(review_id)
    reloaded = load_approval(review_id)
    assert reloaded.state == "draft_generated"


def test_mark_field_changed(review_id):
    mark_field_changed(review_id, "positionen.0.menge")
    rec = load_approval(review_id)
    assert "positionen.0.menge" in rec.changed_fields


def test_mark_field_changed_no_duplicates(review_id):
    mark_field_changed(review_id, "kunde_firma")
    mark_field_changed(review_id, "kunde_firma")
    rec = load_approval(review_id)
    assert rec.changed_fields.count("kunde_firma") == 1


def test_approval_record_round_trip(review_id):
    original = ApprovalRecord(
        state="reviewed",
        approved_by="Tester",
        changed_fields=["f1", "f2"],
    )
    save_approval(review_id, original)
    loaded = load_approval(review_id)
    assert loaded.state == "reviewed"
    assert loaded.approved_by == "Tester"
    assert loaded.changed_fields == ["f1", "f2"]


def test_all_valid_transitions_defined():
    states = {"draft_generated", "reviewed", "approved", "ready_to_send"}
    assert set(VALID_TRANSITIONS.keys()) == states
