"""Deterministic matching against master data.

Three-tier approach (fully auditable, no LLM):
1. Exact match on normalized article number
2. Fuzzy match on article number (typos, OCR errors)
3. Composite match on description + material (last resort)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz, process

from ..core import Position

MatchStatus = Literal["exact", "fuzzy", "semantic", "no_match"]


@dataclass
class MatchResult:
    pos_nr: int
    status: MatchStatus
    score: float  # 0.0 .. 1.0
    matched_artikelnr: str | None = None
    matched_bezeichnung: str | None = None
    matched_row: dict | None = None

    def to_dict(self) -> dict:
        return {
            "pos_nr": self.pos_nr,
            "status": self.status,
            "score": self.score,
            "matched_artikelnr": self.matched_artikelnr,
            "matched_bezeichnung": self.matched_bezeichnung,
            "matched_row": self.matched_row,
        }


def match_positions(
    positions: list[Position],
    stammdaten: list[dict],
    fuzzy_threshold: int = 85,
    semantic_threshold: int = 70,
) -> list[MatchResult]:
    """Match each position against master data."""
    return [
        _match_one(pos, stammdaten, fuzzy_threshold, semantic_threshold)
        for pos in positions
    ]


def _match_one(
    pos: Position,
    stammdaten: list[dict],
    fuzzy_threshold: int,
    semantic_threshold: int,
) -> MatchResult:
    return (
        _exact_match(pos, stammdaten)
        or _fuzzy_match(pos, stammdaten, fuzzy_threshold)
        or _composite_match(pos, stammdaten, semantic_threshold)
        or MatchResult(pos_nr=pos.pos_nr, status="no_match", score=0.0)
    )


def _exact_match(pos: Position, stammdaten: list[dict]) -> MatchResult | None:
    normalized = _normalize(pos.artikelnummer)
    if not normalized:
        return None
    for row in stammdaten:
        if _normalize(row.get("artikel_nr", "")) == normalized:
            return MatchResult(
                pos_nr=pos.pos_nr,
                status="exact",
                score=1.0,
                matched_artikelnr=row.get("artikel_nr", ""),
                matched_bezeichnung=row.get("bezeichnung", ""),
                matched_row=row,
            )
    return None


def _fuzzy_match(pos: Position, stammdaten: list[dict], threshold: int) -> MatchResult | None:
    if not pos.artikelnummer:
        return None
    artikel_nrs = [row.get("artikel_nr", "") for row in stammdaten]
    hit = process.extractOne(pos.artikelnummer, artikel_nrs, scorer=fuzz.ratio)
    if not hit:
        return None
    nr, score, idx = hit
    if score < threshold:
        return None
    return MatchResult(
        pos_nr=pos.pos_nr,
        status="fuzzy",
        score=score / 100.0,
        matched_artikelnr=nr,
        matched_bezeichnung=stammdaten[idx].get("bezeichnung", ""),
        matched_row=stammdaten[idx],
    )


def _composite_match(pos: Position, stammdaten: list[dict], threshold: int) -> MatchResult | None:
    # Weighted: description dominates, material is a tie-breaker.
    best_idx = -1
    best_score = 0.0
    for i, row in enumerate(stammdaten):
        bez_score = fuzz.token_set_ratio(pos.bezeichnung or "", row.get("bezeichnung", ""))
        mat_score = (
            fuzz.token_set_ratio(pos.werkstoff, row["werkstoff"])
            if pos.werkstoff and row.get("werkstoff")
            else 0.0
        )
        combined = 0.75 * bez_score + 0.25 * mat_score
        if combined > best_score:
            best_score = combined
            best_idx = i

    if best_idx < 0 or best_score < threshold:
        return None
    row = stammdaten[best_idx]
    return MatchResult(
        pos_nr=pos.pos_nr,
        status="semantic",
        score=best_score / 100.0,
        matched_artikelnr=row["artikel_nr"],
        matched_bezeichnung=row["bezeichnung"],
        matched_row=row,
    )


def _normalize(s: str) -> str:
    """Uppercase, strip all whitespace. Preserves digits/hyphens/dots."""
    return "".join((s or "").upper().split())
