from __future__ import annotations

from pathlib import Path

from quoting.reviews import Payloads, draft_pdf_filename, scan_reviews


def _seed_review(sqlite_repo, review_id: str = "review-1", *, with_pdf: bool = True) -> Path:
    sqlite_repo.create_review(review_id, subject="Preisanfrage", sender="kunde@example.com")
    folder = sqlite_repo.artifact_dir(review_id)
    sqlite_repo.save_mail(
        review_id,
        {
            "subject": "Preisanfrage",
            "from": "kunde@example.com",
            "body": "Bitte anbieten.",
            "attachments": [],
        },
    )
    sqlite_repo.save_extracted(review_id, {"positionen": []})
    sqlite_repo.save_matches_initial(review_id, [])
    sqlite_repo.save_quotation_initial(review_id, {"gesamtsumme": 0, "waehrung": "EUR"})
    if with_pdf:
        pdf = folder / draft_pdf_filename(review_id)
        pdf.write_bytes(b"%PDF-1.4\n")
        sqlite_repo.register_document(
            review_id,
            kind="draft_pdf",
            path=pdf,
            filename=pdf.name,
            content_type="application/pdf",
        )
    return folder


def test_scan_reviews_marks_approved_review_as_completed(sqlite_repo):
    _seed_review(sqlite_repo)
    sqlite_repo.save_payload(
        "review-1",
        Payloads.APPROVAL,
        {
            "state": "approved",
            "approved_by": "Tester",
            "approved_at": "2026-05-18T10:00:00Z",
        },
    )

    [summary] = scan_reviews()

    assert summary.status == "abgeschlossen"


def test_scan_reviews_keeps_unapproved_draft_in_review_bucket(sqlite_repo):
    _seed_review(sqlite_repo)
    sqlite_repo.save_payload("review-1", Payloads.APPROVAL, {"state": "draft_generated"})

    [summary] = scan_reviews()

    assert summary.status == "pdf_bereit"


def test_scan_reviews_uses_in_progress_for_review_without_pdf(sqlite_repo):
    _seed_review(sqlite_repo, with_pdf=False)
    sqlite_repo.save_payload("review-1", Payloads.APPROVAL, {"state": "draft_generated"})

    [summary] = scan_reviews()

    assert summary.status == "in_arbeit"
