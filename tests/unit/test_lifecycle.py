"""Tests for quoting.reviews.lifecycle — reset_review_artifacts."""
from __future__ import annotations

from pathlib import Path

import pytest

from quoting.api.approval_store import ApprovalStore
from quoting.api.progress_store import ProgressStore
from quoting.reviews import Payloads
from quoting.reviews.lifecycle import reset_review_artifacts


@pytest.fixture
def review(sqlite_repo) -> tuple[str, Path]:
    review_id = "test001"
    sqlite_repo.create_review(review_id, subject="Anfrage", sender="kunde@example.com")
    sqlite_repo.save_mail(
        review_id,
        {
            "subject": "Anfrage",
            "from": "kunde@example.com",
            "body": "Bitte Angebot",
            "attachments": [{"name": "rfq.pdf"}],
        },
    )
    folder = sqlite_repo.artifact_dir(review_id)
    attachment = folder / "rfq.pdf"
    attachment.write_bytes(b"%PDF-test")
    sqlite_repo.register_document(
        review_id,
        kind="attachment",
        path=attachment,
        filename=attachment.name,
        content_type="application/pdf",
    )
    return review_id, folder


def _reset(sqlite_repo, review_id: str) -> None:
    reset_review_artifacts(
        review_id,
        repo=sqlite_repo,
        progress_store=ProgressStore(sqlite_repo),
        approval_store=ApprovalStore(sqlite_repo),
    )


def test_reset_preserves_mail_payload(sqlite_repo, review):
    review_id, _ = review
    _reset(sqlite_repo, review_id)
    assert sqlite_repo.load_mail(review_id) is not None


def test_reset_preserves_attachment(sqlite_repo, review):
    review_id, folder = review
    _reset(sqlite_repo, review_id)
    assert (folder / "rfq.pdf").exists()


def test_reset_deletes_pipeline_payloads(sqlite_repo, review):
    review_id, _ = review
    sqlite_repo.save_extracted(review_id, {})
    sqlite_repo.save_matches_initial(review_id, [])
    sqlite_repo.save_quotation_reviewed(review_id, {})
    _reset(sqlite_repo, review_id)
    assert sqlite_repo.load_payload(review_id, Payloads.EXTRACTED) is None
    assert sqlite_repo.load_payload(review_id, Payloads.MATCHES) is None
    assert sqlite_repo.load_payload(review_id, Payloads.QUOTATION_REVIEWED) is None


def test_reset_deletes_subdirectory(sqlite_repo, review):
    review_id, folder = review
    sub = folder / "pipeline"
    sub.mkdir()
    (sub / "step.json").write_text("{}", encoding="utf-8")
    _reset(sqlite_repo, review_id)
    assert not sub.exists()


def test_reset_creates_fresh_progress(sqlite_repo, review):
    review_id, _ = review
    _reset(sqlite_repo, review_id)
    data = ProgressStore(sqlite_repo).read(review_id)
    assert data is not None
    assert data["status"] == "running"
    assert data["review_id"] == review_id


def test_reset_creates_fresh_approval(sqlite_repo, review):
    review_id, _ = review
    _reset(sqlite_repo, review_id)
    assert ApprovalStore(sqlite_repo).load(review_id).state == "draft_generated"


def test_reset_unknown_review_is_noop(sqlite_repo):
    sqlite_repo.create_review("unknown")
    _reset(sqlite_repo, "unknown")  # must not raise
