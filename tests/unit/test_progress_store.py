"""Tests for quoting.api.progress_store."""
from __future__ import annotations

import pytest

from quoting.api.progress_store import (
    PIPELINE_STEPS,
    complete_progress,
    fail_progress,
    init_progress,
    read_progress,
    update_step,
    write_progress,
)


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review_prog")
    return "review_prog"


def test_init_creates_progress_payload(review_id):
    data = init_progress(review_id)
    assert read_progress(review_id) is not None
    assert data["review_id"] == review_id
    assert data["status"] == "running"
    assert data["progress_percent"] == 0


def test_init_sets_created_at(review_id):
    data = init_progress(review_id)
    assert "created_at" in data
    assert data["created_at"] is not None


def test_init_creates_all_pipeline_steps(review_id):
    data = init_progress(review_id)
    step_names = [s["name"] for s in data["steps"]]
    assert step_names == PIPELINE_STEPS


def test_read_progress_returns_none_when_missing(review_id):
    assert read_progress(review_id) is None


def test_read_progress_after_init(review_id):
    init_progress(review_id)
    data = read_progress(review_id)
    assert data is not None
    assert data["review_id"] == review_id


def test_update_step_marks_running(review_id):
    init_progress(review_id)
    update_step(review_id, "Extraktion", "started", "LLM läuft")
    data = read_progress(review_id)
    step = next(s for s in data["steps"] if s["name"] == "Extraktion")
    assert step["status"] == "running"
    assert step["detail"] == "LLM läuft"


def test_update_step_advances_percent(review_id):
    init_progress(review_id)
    update_step(review_id, "Mail vorbereiten", "completed", "")
    data = read_progress(review_id)
    assert data["progress_percent"] > 0


def test_complete_progress(review_id):
    init_progress(review_id)
    complete_progress(review_id, {"draft_pdf_url": "/pdf/draft.pdf"})
    data = read_progress(review_id)
    assert data["status"] == "completed"
    assert data["progress_percent"] == 100
    assert data["result"]["draft_pdf_url"] == "/pdf/draft.pdf"
    for step in data["steps"]:
        assert step["status"] in ("completed", "skipped")


def test_fail_progress(review_id):
    init_progress(review_id)
    update_step(review_id, "Extraktion", "started", "")
    fail_progress(review_id, "LLM API timeout")
    data = read_progress(review_id)
    assert data["status"] == "failed"
    assert data["error"] == "LLM API timeout"


def test_write_progress_roundtrip(review_id):
    init_progress(review_id)
    data = read_progress(review_id)
    data["custom_field"] = "hello"
    write_progress(review_id, data)
    reloaded = read_progress(review_id)
    assert reloaded["custom_field"] == "hello"
