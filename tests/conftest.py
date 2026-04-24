"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from quoting.core import Anfrage, Position
from quoting.matching import MatchResult


def _make_position(**over) -> Position:
    base = dict(
        pos_nr=1, artikelnummer="X", bezeichnung="b",
        menge=1, einheit="Stk", confidence="high", source_quote="q",
    )
    base.update(over)
    return Position(**base)


@pytest.fixture
def make_position():
    """Factory for building a Position with sensible defaults."""
    return _make_position


@pytest.fixture
def sample_stammdaten() -> list[dict]:
    return [
        {
            "artikel_nr": "001GLP108015",
            "bezeichnung": "Gleitstück PTFE 108x15",
            "werkstoff": "PTFE",
            "basispreis_eur": "100.00",
            "zkalk_offset_eur": "5.00",
        },
        {
            "artikel_nr": "002GLS082003",
            "bezeichnung": "Gleitstück variabel 108x15",
            "werkstoff": "PTFE",
            "basispreis_eur": "28.75",
            "zkalk_offset_eur": "1.80",
        },
        {
            "artikel_nr": "001APZ00031B",
            "bezeichnung": "Abnahmeprüfzeugnis 3.1",
            "werkstoff": "-",
            "basispreis_eur": "45.00",
            "zkalk_offset_eur": "0.00",
        },
    ]


@pytest.fixture
def sample_anfrage():
    return Anfrage(
        kunde_firma="Testkunde GmbH",
        belegnummer="RFQ-2024-001",
        positionen=[_make_position(pos_nr=10, artikelnummer="001GLP108015", menge=100)],
    )


@pytest.fixture
def exact_match_factory():
    """Build a MatchResult marked as exact for a given master-data row."""
    def _build(row: dict, pos_nr: int = 1) -> MatchResult:
        return MatchResult(
            pos_nr=pos_nr, status="exact", score=1.0,
            matched_artikelnr=row["artikel_nr"],
            matched_bezeichnung=row["bezeichnung"],
            matched_row=row,
        )
    return _build
