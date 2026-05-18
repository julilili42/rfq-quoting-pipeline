from __future__ import annotations

from pathlib import Path

from quoting.reviews import draft_pdf_filename, scan_reviews, write_json


def _review_folder(tmp_path: Path, review_id: str = "review-1") -> Path:
    folder = tmp_path / review_id
    folder.mkdir()
    write_json(
        folder / "mail.json",
        {
            "subject": "Preisanfrage",
            "from": "kunde@example.com",
            "body": "Bitte anbieten.",
            "attachments": [],
        },
    )
    write_json(folder / "01_extracted.json", {"positionen": []})
    write_json(folder / "02_matches.json", [])
    write_json(folder / "03_quotation.json", {"gesamtsumme": 0, "waehrung": "EUR"})
    (folder / draft_pdf_filename(review_id)).write_bytes(b"%PDF-1.4\n")
    return folder


def test_scan_reviews_marks_approved_review_as_completed(tmp_path):
    folder = _review_folder(tmp_path)
    write_json(
        folder / "approval.json",
        {
            "state": "approved",
            "approved_by": "Tester",
            "approved_at": "2026-05-18T10:00:00Z",
        },
    )

    [summary] = scan_reviews(tmp_path)

    assert summary.status == "abgeschlossen"


def test_scan_reviews_keeps_unapproved_draft_in_review_bucket(tmp_path):
    folder = _review_folder(tmp_path)
    write_json(folder / "approval.json", {"state": "draft_generated"})
    write_json(folder / "review_state.json", {"review_id": "review-1"})

    [summary] = scan_reviews(tmp_path)

    assert summary.status == "pdf_bereit"


def test_scan_reviews_uses_in_progress_for_review_without_pdf(tmp_path):
    folder = _review_folder(tmp_path)
    (folder / draft_pdf_filename("review-1")).unlink()
    write_json(folder / "approval.json", {"state": "draft_generated"})

    [summary] = scan_reviews(tmp_path)

    assert summary.status == "in_arbeit"
