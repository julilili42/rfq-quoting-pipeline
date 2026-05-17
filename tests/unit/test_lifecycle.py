"""Tests for quoting.reviews.lifecycle — reset_review_artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from quoting.reviews.lifecycle import reset_review_artifacts


def _make_review(tmp_path: Path, review_id: str = "test001") -> Path:
    folder = tmp_path / review_id
    folder.mkdir()
    mail_json = folder / "mail.json"
    mail_json.write_text(
        json.dumps(
            {
                "subject": "Anfrage",
                "from": "kunde@example.com",
                "body": "Bitte Angebot",
                "attachments": [{"name": "rfq.pdf"}],
            }
        ),
        encoding="utf-8",
    )
    (folder / "rfq.pdf").write_bytes(b"%PDF-test")
    return folder


def test_reset_preserves_mail_json(tmp_path):
    folder = _make_review(tmp_path)
    reset_review_artifacts(folder, "test001")
    assert (folder / "mail.json").exists()


def test_reset_preserves_attachment(tmp_path):
    folder = _make_review(tmp_path)
    reset_review_artifacts(folder, "test001")
    assert (folder / "rfq.pdf").exists()


def test_reset_deletes_pipeline_artifacts(tmp_path):
    folder = _make_review(tmp_path)
    (folder / "01_extracted.json").write_text("{}", encoding="utf-8")
    (folder / "02_matches.json").write_text("[]", encoding="utf-8")
    (folder / "quotation_reviewed.json").write_text("{}", encoding="utf-8")
    reset_review_artifacts(folder, "test001")
    assert not (folder / "01_extracted.json").exists()
    assert not (folder / "02_matches.json").exists()
    assert not (folder / "quotation_reviewed.json").exists()


def test_reset_deletes_subdirectory(tmp_path):
    folder = _make_review(tmp_path)
    sub = folder / "pipeline"
    sub.mkdir()
    (sub / "step.json").write_text("{}", encoding="utf-8")
    reset_review_artifacts(folder, "test001")
    assert not sub.exists()


def test_reset_creates_fresh_progress(tmp_path):
    folder = _make_review(tmp_path)
    reset_review_artifacts(folder, "test001")
    progress_path = folder / "progress.json"
    assert progress_path.exists()
    data = json.loads(progress_path.read_text())
    assert data["status"] == "running"
    assert data["review_id"] == "test001"


def test_reset_creates_fresh_approval(tmp_path):
    folder = _make_review(tmp_path)
    reset_review_artifacts(folder, "test001")
    approval_path = folder / "approval.json"
    assert approval_path.exists()
    data = json.loads(approval_path.read_text())
    assert data["state"] == "draft_generated"


def test_reset_nonexistent_folder_is_noop(tmp_path):
    folder = tmp_path / "doesnotexist"
    reset_review_artifacts(folder, "x")  # must not raise


def test_reset_without_mail_json(tmp_path):
    folder = tmp_path / "bare"
    folder.mkdir()
    (folder / "01_extracted.json").write_text("{}", encoding="utf-8")
    reset_review_artifacts(folder, "bare")
    assert not (folder / "01_extracted.json").exists()
