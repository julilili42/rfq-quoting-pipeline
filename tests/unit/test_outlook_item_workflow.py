"""Service-level tests for the outlook-item ↔ review binding.

Covers get_outlook_item_status (the compact payload the Outlook add-in
polls) and detach_outlook_item (the reset path). The pipeline dependency
is mocked because none of these methods touch it.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quoting.api.services.review_workflow_service import ReviewWorkflowService


@pytest.fixture
def workflow_service(sqlite_repo) -> ReviewWorkflowService:
    return ReviewWorkflowService(
        repo=sqlite_repo,
        pipeline=MagicMock(),
        review_ui_base_url="http://localhost:5174",
    )


def test_status_is_none_when_no_review_bound(workflow_service):
    assert workflow_service.get_outlook_item_status("unknown-item") is None


def test_status_payload_for_fresh_review(workflow_service, sqlite_repo):
    sqlite_repo.create_review(
        "review-1",
        subject="Anfrage 42",
        sender="kunde@example.com",
        outlook_item_id="item-A",
    )

    status = workflow_service.get_outlook_item_status("item-A")
    assert status is not None
    assert status["review_id"] == "review-1"
    assert status["subject"] == "Anfrage 42"
    assert status["sender"] == "kunde@example.com"
    assert status["approval_state"] == "draft_generated"
    assert status["opened_at"] is None
    assert status["approved_at"] is None
    assert status["sent_at"] is None
    assert status["review_url"].endswith("review_id=review-1")


def test_status_reflects_opened_and_approved_timestamps(workflow_service, sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="item-A")
    workflow_service.mark_review_opened("review-1")
    workflow_service.transition_approval(
        "review-1",
        target="approved",
        actor="lena@example.com",
    )

    status = workflow_service.get_outlook_item_status("item-A")
    assert status["opened_at"] is not None
    assert status["approved_at"] is not None
    assert status["approved_by"] == "lena@example.com"
    assert status["approval_state"] == "approved"


def test_status_includes_kunden_firma_when_extracted(workflow_service, sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="item-A")
    sqlite_repo.save_anfrage_reviewed(
        "review-1",
        {"kunde_firma": "ACME GmbH", "positionen": []},
    )

    status = workflow_service.get_outlook_item_status("item-A")
    assert status["kunden_firma"] == "ACME GmbH"


def test_detach_unlinks_but_preserves_review(workflow_service, sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="item-A")

    result = workflow_service.detach_outlook_item("item-A")
    assert result == {"review_id": "review-1"}

    # Lookup is now empty …
    assert workflow_service.get_outlook_item_status("item-A") is None
    # … but the review row itself is still there for the overview.
    assert sqlite_repo.get_review("review-1") is not None


def test_detach_is_noop_when_nothing_bound(workflow_service):
    assert workflow_service.detach_outlook_item("unknown-item") is None
