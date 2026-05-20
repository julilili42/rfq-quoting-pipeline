"""Round-trip tests for REQUIREMENTS_ACKNOWLEDGED payload accessors."""
from __future__ import annotations


def test_load_returns_empty_when_unset(sqlite_repo):
    sqlite_repo.ensure_review("r1")
    assert sqlite_repo.load_requirements_acknowledged("r1") == []


def test_save_and_load_indices_round_trip(sqlite_repo):
    sqlite_repo.ensure_review("r2")
    sqlite_repo.save_requirements_acknowledged("r2", [2, 0, 1])
    assert sqlite_repo.load_requirements_acknowledged("r2") == [0, 1, 2]


def test_save_dedupes_and_drops_negatives(sqlite_repo):
    sqlite_repo.ensure_review("r3")
    sqlite_repo.save_requirements_acknowledged("r3", [1, 1, -1, 3, 3])
    assert sqlite_repo.load_requirements_acknowledged("r3") == [1, 3]


def test_save_empty_clears(sqlite_repo):
    sqlite_repo.ensure_review("r4")
    sqlite_repo.save_requirements_acknowledged("r4", [0, 1])
    sqlite_repo.save_requirements_acknowledged("r4", [])
    assert sqlite_repo.load_requirements_acknowledged("r4") == []
