"""
Pricing-Modul
=============
Preisberechnung für eine Anfrage. Deterministisch, KEIN LLM.

Logik (Mock für SAP ZKALK):
  - Basispreis aus Stammdaten
  - Mengenstaffel-Rabatt
  - ZKALK-Offset addieren
  - Summe = Einzelpreis * Menge
"""
from pathlib import Path
from typing import TypedDict
import csv

from extractor import Anfrage


class QuotationItem(TypedDict):
    pos_nr: int
    artikel_nr: str
    bezeichnung: str
    menge: float
    einheit: str
    einzelpreis: float
    rabatt_prozent: float
    gesamtpreis: float
    bemerkung: str  # z.B. "Preis geschätzt - kein exakter Match"


def lade_preise(pfad: Path) -> dict[str, dict]:
    """Lädt Preistabelle als Dict: artikel_nr -> {basispreis, zkalk_offset}."""
    if not pfad.exists():
        return {}  # Preise kommen dann aus matched_row (Stammdaten)
    preise: dict[str, dict] = {}
    with open(pfad, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            preise[row["artikel_nr"]] = {
                "basispreis": float(row.get("basispreis_eur", 0)),
                "zkalk_offset": float(row.get("zkalk_offset_eur", 0)),
            }
    return preise


def berechne_mengenstaffel(menge: float) -> float:
    """Gibt Rabatt als Dezimalzahl zurück (0.10 = 10%)."""
    if menge >= 1000:
        return 0.15
    if menge >= 500:
        return 0.10
    if menge >= 100:
        return 0.05
    return 0.0


def berechne_quotation(
    anfrage: Anfrage,
    matches: list[dict],
    preise_pfad: Path,
) -> dict:
    """
    Berechnet ein komplettes Angebot für die Anfrage.
    Kombiniert Extraktion + Matching + Preisdaten.
    """
    preise_external = lade_preise(preise_pfad)
    items: list[QuotationItem] = []
    gesamt = 0.0
    warnungen: list[str] = []

    for pos, match in zip(anfrage.positionen, matches):
        artikel_nr = match.get(
            "matched_artikelnr") or pos.artikelnummer or "N/A"
        bezeichnung = match.get("matched_bezeichnung") or pos.bezeichnung

        # Preisermittlung: erst externe Preistabelle, dann Stammdaten-Row
        basispreis = 0.0
        zkalk_offset = 0.0
        bemerkung = ""

        if match["status"] == "no_match":
            bemerkung = "Kein Stammdaten-Match - Preis manuell prüfen!"
            warnungen.append(f"Pos {pos.pos_nr}: Kein Match")
        elif match["status"] in ("fuzzy", "semantic"):
            bemerkung = f"Unscharfer Match (Score {match['score']:.0%}) - prüfen!"
            warnungen.append(
                f"Pos {pos.pos_nr}: Unscharfer Match auf {artikel_nr}")

        # Preis holen
        if artikel_nr in preise_external:
            basispreis = preise_external[artikel_nr]["basispreis"]
            zkalk_offset = preise_external[artikel_nr]["zkalk_offset"]
        elif match.get("matched_row"):
            row = match["matched_row"]
            basispreis = float(row.get("basispreis_eur", 0))
            zkalk_offset = float(row.get("zkalk_offset_eur", 0))

        # Staffel-Rabatt
        rabatt = berechne_mengenstaffel(pos.menge)
        einzelpreis = basispreis * (1 - rabatt) + zkalk_offset
        gesamtpreis = einzelpreis * pos.menge

        items.append(QuotationItem(
            pos_nr=pos.pos_nr,
            artikel_nr=artikel_nr,
            bezeichnung=bezeichnung,
            menge=pos.menge,
            einheit=pos.einheit,
            einzelpreis=round(einzelpreis, 2),
            rabatt_prozent=round(rabatt * 100, 1),
            gesamtpreis=round(gesamtpreis, 2),
            bemerkung=bemerkung,
        ))
        gesamt += gesamtpreis

    return {
        "kunde_firma": anfrage.kunde_firma,
        "kunde_ansprechpartner": anfrage.kunde_ansprechpartner,
        "kunde_email": anfrage.kunde_email,
        "belegnummer": anfrage.belegnummer,
        "incoterms": anfrage.incoterms,
        "zahlungsbedingungen": anfrage.zahlungsbedingungen,
        "items": items,
        "gesamtsumme": round(gesamt, 2),
        "waehrung": "EUR",
        "warnungen": warnungen,
    }
