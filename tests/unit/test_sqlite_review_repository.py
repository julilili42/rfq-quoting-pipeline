from __future__ import annotations

from quoting.api.progress_store import init_progress, read_progress
from quoting.reviews import Payloads, find_draft_pdf


def test_mail_payload_round_trips(sqlite_repo):
    sqlite_repo.create_review("review-1", subject="Anfrage", sender="kunde@example.com")

    sqlite_repo.save_mail(
        "review-1", {"subject": "Anfrage", "from": "kunde@example.com"}
    )

    assert sqlite_repo.load_mail("review-1") == {
        "subject": "Anfrage",
        "from": "kunde@example.com",
    }


def test_save_mail_mirrors_subject_and_sender_to_reviews_row(sqlite_repo):
    sqlite_repo.create_review("review-1")
    sqlite_repo.save_mail(
        "review-1",
        {"subject": "Neu", "from": "buyer@example.com", "body": "Hallo"},
    )

    row = sqlite_repo.get_review("review-1")
    assert row["subject"] == "Neu"
    assert row["sender"] == "buyer@example.com"
    assert row["body"] == "Hallo"


def test_progress_is_stored_in_sqlite(sqlite_repo):
    sqlite_repo.create_review("review-1")

    init_progress("review-1")

    assert read_progress("review-1")["status"] == "running"


def test_legacy_payload_names_are_renamed_on_startup(tmp_path, monkeypatch):
    """Old ``mail.json``-style keys are rewritten when the repo opens."""
    import sqlite3

    from quoting.reviews.sqlite_repository import (
        SQLiteReviewRepository,
        reset_default_repository,
    )

    db_path = tmp_path / "quoting.sqlite"
    monkeypatch.setenv("QUOTING_DB_PATH", str(db_path))
    monkeypatch.setenv("QUOTING_ARTIFACT_ROOT", str(tmp_path / "artifacts" / "reviews"))
    reset_default_repository()

    # Seed the DB with the old naming convention, then re-open.
    repo = SQLiteReviewRepository(db_path)
    repo.create_review("review-1")
    now = "2026-05-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO review_payloads VALUES (?, ?, ?, ?, ?)",
            ("review-1", "mail.json", '{"subject":"X"}', now, now),
        )
        conn.execute(
            "INSERT INTO review_payloads VALUES (?, ?, ?, ?, ?)",
            ("review-1", "01_extracted.json", '{"positionen":[]}', now, now),
        )

    reset_default_repository()
    repo = SQLiteReviewRepository(db_path)

    assert repo.load_payload("review-1", Payloads.MAIL) == {"subject": "X"}
    assert repo.load_payload("review-1", Payloads.EXTRACTED) == {"positionen": []}
    assert repo.load_payload("review-1", "mail.json") is None
    reset_default_repository()


def test_registered_draft_pdf_is_resolved_from_sqlite(sqlite_repo):
    sqlite_repo.create_review("review-1")
    folder = sqlite_repo.artifact_dir("review-1")
    pdf = folder / "pipeline" / "pipeline_ANGEBOT_DRAFT.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n")

    sqlite_repo.register_document(
        "review-1",
        kind="draft_pdf",
        path=pdf,
        filename=pdf.name,
        content_type="application/pdf",
    )

    assert find_draft_pdf("review-1") == pdf
