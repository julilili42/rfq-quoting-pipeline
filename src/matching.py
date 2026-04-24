"""
Matching-Modul
==============
Deterministisches Matching extrahierter Positionen gegen Stammdaten.
Drei-Stufen-Ansatz:
  1. Exakter Match auf Artikelnummer
  2. Fuzzy-Match (Typos, Sub-/Superstrings)
  3. Semantischer Match auf Bezeichnung (Embeddings) - optional

Das ist bewusst KEIN LLM-Job: Matching muss reproduzierbar und auditierbar sein.
"""
from pathlib import Path
from typing import TypedDict, Literal
import csv

from rapidfuzz import process, fuzz

from extractor import Position


class MatchResult(TypedDict):
    pos_nr: int
    status: Literal["exact", "fuzzy", "semantic", "no_match"]
    score: float
    matched_artikelnr: str | None
    matched_bezeichnung: str | None
    matched_row: dict | None


def lade_stammdaten(pfad: Path) -> list[dict]:
    """
    Lädt Stammdaten aus CSV. Erwartetes Schema:
      artikel_nr, bezeichnung, werkstoff, basispreis_eur, zkalk_offset_eur
    """
    if not pfad.exists():
        # Mock-Stammdaten für Demo, falls Datei fehlt
        return _mock_stammdaten()

    stammdaten: list[dict] = []
    with open(pfad, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stammdaten.append(row)
    return stammdaten


def _mock_stammdaten() -> list[dict]:
    """Mock-Stammdaten für die Demo mit dem Göhmann-PDF."""
    return [
        {
            "artikel_nr": "001GLP108015",
            "bezeichnung": "Gleitstück für Wiegenträger PTFE/Graphit 108x15",
            "werkstoff": "PTFE mit 15% Graphit",
            "basispreis_eur": "24.50",
            "zkalk_offset_eur": "1.20",
        },
        {
            "artikel_nr": "002GLS082003",
            "bezeichnung": "Gleitstück für Wiegenträger variabler Werkstoff 108x15",
            "werkstoff": "PTFE (diverse Compound-Optionen)",
            "basispreis_eur": "28.75",
            "zkalk_offset_eur": "1.80",
        },
        {
            "artikel_nr": "001APZ00031B",
            "bezeichnung": "Abnahmeprüfzeugnis DIN EN 10204:2005-01 3.1",
            "werkstoff": "-",
            "basispreis_eur": "45.00",
            "zkalk_offset_eur": "0.00",
        },
    ]


def match_positionen(
    positionen: list[Position],
    stammdaten: list[dict],
    fuzzy_threshold: int = 85,
) -> list[MatchResult]:
    """Matcht jede Position gegen die Stammdaten."""
    return [_match_eine(pos, stammdaten, fuzzy_threshold) for pos in positionen]


def _match_eine(
    pos: Position,
    stammdaten: list[dict],
    fuzzy_threshold: int,
) -> MatchResult:
    """Match-Logik für eine einzelne Position."""
    artikel_nrs = [row["artikel_nr"] for row in stammdaten]

    # 1. Exact Match auf Artikelnummer (case-insensitive, Leerzeichen ignoriert)
    normalized = _normalize(pos.artikelnummer)
    for i, nr in enumerate(artikel_nrs):
        if _normalize(nr) == normalized and normalized:
            return MatchResult(
                pos_nr=pos.pos_nr,
                status="exact",
                score=1.0,
                matched_artikelnr=nr,
                matched_bezeichnung=stammdaten[i]["bezeichnung"],
                matched_row=stammdaten[i],
            )

    # 2. Fuzzy Match auf Artikelnummer
    if pos.artikelnummer:
        match = process.extractOne(
            pos.artikelnummer, artikel_nrs, scorer=fuzz.ratio)
        if match:
            nr, score, idx = match
            if score >= fuzzy_threshold:
                return MatchResult(
                    pos_nr=pos.pos_nr,
                    status="fuzzy",
                    score=score / 100.0,
                    matched_artikelnr=nr,
                    matched_bezeichnung=stammdaten[idx]["bezeichnung"],
                    matched_row=stammdaten[idx],
                )

    # 3. Semantisch via Bezeichnung (Fallback, bewusst einfach gehalten)
    bezeichnungen = [row["bezeichnung"] for row in stammdaten]
    match = process.extractOne(
        pos.bezeichnung, bezeichnungen, scorer=fuzz.token_set_ratio)
    if match:
        bez, score, idx = match
        if score >= 70:  # Niedrigere Schwelle weil Freitext
            return MatchResult(
                pos_nr=pos.pos_nr,
                status="semantic",
                score=score / 100.0,
                matched_artikelnr=stammdaten[idx]["artikel_nr"],
                matched_bezeichnung=bez,
                matched_row=stammdaten[idx],
            )

    # 4. Kein Match
    return MatchResult(
        pos_nr=pos.pos_nr,
        status="no_match",
        score=0.0,
        matched_artikelnr=None,
        matched_bezeichnung=None,
        matched_row=None,
    )


def _normalize(s: str) -> str:
    """Normalisiert Artikelnummern für Vergleich."""
    return "".join(s.upper().split()) if s else ""
