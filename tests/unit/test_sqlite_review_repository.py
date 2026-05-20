from __future__ import annotations

from quoting.api.progress_store import ProgressStore
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

    progress_store = ProgressStore(sqlite_repo)
    progress_store.init("review-1")

    assert progress_store.read("review-1")["status"] == "running"


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


def test_create_review_stores_outlook_item_id(sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="AAMkAGI2-test")
    row = sqlite_repo.get_review("review-1")
    assert row["outlook_item_id"] == "AAMkAGI2-test"


def test_create_review_without_outlook_item_id_leaves_it_null(sqlite_repo):
    sqlite_repo.create_review("review-1")
    row = sqlite_repo.get_review("review-1")
    assert row["outlook_item_id"] is None


def test_get_review_by_outlook_item_id_returns_bound_review(sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="item-A")
    sqlite_repo.create_review("review-2", outlook_item_id="item-B")

    found = sqlite_repo.get_review_by_outlook_item_id("item-A")
    assert found is not None
    assert found["review_id"] == "review-1"


def test_get_review_by_outlook_item_id_returns_none_when_unbound(sqlite_repo):
    sqlite_repo.create_review("review-1")
    assert sqlite_repo.get_review_by_outlook_item_id("nonexistent") is None


def test_get_review_by_outlook_item_id_prefers_most_recent(sqlite_repo):
    """If multiple reviews share an Outlook item, the freshest wins."""
    import time

    sqlite_repo.create_review("review-old", outlook_item_id="item-A")
    time.sleep(0.01)  # ensure updated_at differs
    sqlite_repo.create_review("review-new", outlook_item_id="item-A")

    found = sqlite_repo.get_review_by_outlook_item_id("item-A")
    assert found is not None
    assert found["review_id"] == "review-new"


def test_set_outlook_item_id_can_detach(sqlite_repo):
    sqlite_repo.create_review("review-1", outlook_item_id="item-A")
    sqlite_repo.set_outlook_item_id("review-1", None)

    assert sqlite_repo.get_review_by_outlook_item_id("item-A") is None
    row = sqlite_repo.get_review("review-1")
    assert row is not None  # review preserved
    assert row["outlook_item_id"] is None


def test_outlook_item_id_migration_on_existing_db(tmp_path, monkeypatch):
    """An existing DB without the column gets it added on next open."""
    import sqlite3

    from quoting.reviews.sqlite_repository import (
        SQLiteReviewRepository,
        reset_default_repository,
    )

    db_path = tmp_path / "quoting.sqlite"
    monkeypatch.setenv("QUOTING_DB_PATH", str(db_path))
    monkeypatch.setenv("QUOTING_ARTIFACT_ROOT", str(tmp_path / "artifacts" / "reviews"))
    reset_default_repository()

    # Hand-craft an old-shape `reviews` table without outlook_item_id.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE reviews (
                review_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL DEFAULT '',
                sender TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'api',
                status TEXT NOT NULL DEFAULT 'running',
                approval_state TEXT NOT NULL DEFAULT 'draft_generated',
                final_pdf_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO reviews (review_id, created_at, updated_at) VALUES (?, ?, ?)",
            ("legacy-review", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )

    # Opening the repo runs the migration.
    repo = SQLiteReviewRepository(db_path)
    repo.set_outlook_item_id("legacy-review", "item-A")
    assert repo.get_review_by_outlook_item_id("item-A")["review_id"] == "legacy-review"
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
