"""Tests for quoting.api.approval_store — state machine transitions."""
from __future__ import annotations

from pathlib import Path

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
def review_dir(tmp_path: Path) -> Path:
    d = tmp_path / "review_001"
    d.mkdir()
    return d


def test_fresh_review_is_draft_generated(review_dir):
    rec = load_approval(review_dir)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None
    assert rec.history == []


def test_transition_draft_to_reviewed(review_dir):
    rec = transition(review_dir, "reviewed", actor="KAM")
    assert rec.state == "reviewed"
    assert len(rec.history) == 1
    assert rec.history[0]["from"] == "draft_generated"
    assert rec.history[0]["to"] == "reviewed"
    assert rec.history[0]["actor"] == "KAM"


def test_transition_reviewed_to_approved_sets_fields(review_dir):
    transition(review_dir, "reviewed")
    rec = transition(review_dir, "approved", actor="Max Mustermann")
    assert rec.state == "approved"
    assert rec.approved_by == "Max Mustermann"
    assert rec.approved_at is not None


def test_transition_approved_to_ready_to_send(review_dir):
    transition(review_dir, "reviewed")
    transition(review_dir, "approved", actor="K")
    rec = transition(review_dir, "ready_to_send")
    assert rec.state == "ready_to_send"
    assert rec.sent_at is not None


def test_final_pdf_path_stored(review_dir):
    rec = transition(review_dir, "approved", final_pdf_path="final.pdf")
    assert rec.final_pdf_path == "final.pdf"


def test_invalid_transition_is_rejected(review_dir):
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(review_dir, "ready_to_send")  # skip reviewed & approved


def test_reset_returns_to_draft_generated(review_dir):
    transition(review_dir, "reviewed")
    transition(review_dir, "approved", actor="X")
    rec = reset_approval(review_dir)
    assert rec.state == "draft_generated"
    assert rec.approved_by is None


def test_reset_persists_to_disk(review_dir):
    transition(review_dir, "approved")
    reset_approval(review_dir)
    reloaded = load_approval(review_dir)
    assert reloaded.state == "draft_generated"


def test_mark_field_changed(review_dir):
    mark_field_changed(review_dir, "positionen.0.menge")
    rec = load_approval(review_dir)
    assert "positionen.0.menge" in rec.changed_fields


def test_mark_field_changed_no_duplicates(review_dir):
    mark_field_changed(review_dir, "kunde_firma")
    mark_field_changed(review_dir, "kunde_firma")
    rec = load_approval(review_dir)
    assert rec.changed_fields.count("kunde_firma") == 1


def test_approval_record_round_trip(review_dir):
    original = ApprovalRecord(
        state="reviewed",
        approved_by="Tester",
        changed_fields=["f1", "f2"],
    )
    save_approval(review_dir, original)
    loaded = load_approval(review_dir)
    assert loaded.state == "reviewed"
    assert loaded.approved_by == "Tester"
    assert loaded.changed_fields == ["f1", "f2"]


def test_all_valid_transitions_defined():
    states = {"draft_generated", "reviewed", "approved", "ready_to_send"}
    assert set(VALID_TRANSITIONS.keys()) == states
