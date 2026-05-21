"""Tests for quoting.api.progress_store."""
from __future__ import annotations

import pytest

from quoting.api.progress_store import (
    PIPELINE_STEPS,
    ProgressStore,
)


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review_prog")
    return "review_prog"


@pytest.fixture
def progress_store(sqlite_repo) -> ProgressStore:
    return ProgressStore(sqlite_repo)


def test_init_creates_progress_payload(review_id, progress_store):
    data = progress_store.init(review_id)
    assert progress_store.read(review_id) is not None
    assert data["review_id"] == review_id
    assert data["status"] == "running"
    assert data["progress_percent"] == 0


def test_init_sets_created_at(review_id, progress_store):
    data = progress_store.init(review_id)
    assert "created_at" in data
    assert data["created_at"] is not None


def test_init_creates_all_pipeline_steps(review_id, progress_store):
    data = progress_store.init(review_id)
    step_names = [s["name"] for s in data["steps"]]
    assert step_names == PIPELINE_STEPS
    first_step = data["steps"][0]
    assert first_step["started_at"] == data["created_at"]
    assert first_step["completed_at"] is None


def test_read_progress_returns_none_when_missing(review_id, progress_store):
    assert progress_store.read(review_id) is None


def test_read_progress_after_init(review_id, progress_store):
    progress_store.init(review_id)
    data = progress_store.read(review_id)
    assert data is not None
    assert data["review_id"] == review_id


def test_update_step_marks_running(review_id, progress_store):
    progress_store.init(review_id)
    progress_store.update_step(review_id, "Extraktion", "started", "LLM läuft")
    data = progress_store.read(review_id)
    step = next(s for s in data["steps"] if s["name"] == "Extraktion")
    assert step["status"] == "running"
    assert step["detail"] == "LLM läuft"
    assert step["started_at"] is not None
    assert step["completed_at"] is None


def test_update_step_advances_percent(review_id, progress_store):
    progress_store.init(review_id)
    progress_store.update_step(review_id, "Mail vorbereiten", "completed", "")
    data = progress_store.read(review_id)
    step = next(s for s in data["steps"] if s["name"] == "Mail vorbereiten")
    assert data["progress_percent"] > 0
    assert step["completed_at"] is not None


def test_update_step_completion_sets_missing_started_at(review_id, progress_store):
    progress_store.init(review_id)
    progress_store.update_step(review_id, "Extraktion", "completed", "Fast-Path")
    data = progress_store.read(review_id)
    step = next(s for s in data["steps"] if s["name"] == "Extraktion")
    assert step["started_at"] is not None
    assert step["completed_at"] is not None


def test_complete_progress(review_id, progress_store):
    progress_store.init(review_id)
    progress_store.complete(review_id, {"draft_pdf_url": "/pdf/draft.pdf"})
    data = progress_store.read(review_id)
    assert data["status"] == "completed"
    assert data["progress_percent"] == 100
    assert data["result"]["draft_pdf_url"] == "/pdf/draft.pdf"
    for step in data["steps"]:
        assert step["status"] in ("completed", "skipped")


def test_fail_progress(review_id, progress_store):
    progress_store.init(review_id)
    progress_store.update_step(review_id, "Extraktion", "started", "")
    progress_store.fail(review_id, "LLM API timeout")
    data = progress_store.read(review_id)
    assert data["status"] == "failed"
    assert data["error"] == "LLM API timeout"


def test_write_progress_roundtrip(review_id, progress_store):
    progress_store.init(review_id)
    data = progress_store.read(review_id)
    data["custom_field"] = "hello"
    progress_store.write(review_id, data)
    reloaded = progress_store.read(review_id)
    assert reloaded["custom_field"] == "hello"
