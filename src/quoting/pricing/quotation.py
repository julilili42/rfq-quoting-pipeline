"""Quotation building: Anfrage + matches + prices -> Quotation.

Rules:
- Base price from external price table OR master-data row
- Volume discount via tier table
- SAP ZKALK offset added per piece
- Certificates: flat price, no discount, no per-piece multiplier
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..core import Anfrage, Position
from ..matching import MatchResult
from .discounts import volume_discount
from .prices import load_prices


@dataclass
class QuotationItem:
    pos_nr: int
    artikel_nr: str
    bezeichnung: str
    menge: float
    einheit: str
    einzelpreis: float
    rabatt_prozent: float
    gesamtpreis: float
    bemerkung: str


@dataclass
class Quotation:
    kunde_firma: str | None
    kunde_ansprechpartner: str | None
    kunde_email: str | None
    belegnummer: str | None
    incoterms: str | None
    zahlungsbedingungen: str | None
    items: list[QuotationItem]
    gesamtsumme: float
    waehrung: str
    warnungen: list[str]

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "items"},
            "items": [asdict(it) for it in self.items],
        }


def build_quotation(
    anfrage: Anfrage,
    matches: list[MatchResult],
    prices_path: Path,
) -> Quotation:
    """Combine extraction + matches + price data into a Quotation."""
    price_overrides = load_prices(prices_path)
    items: list[QuotationItem] = []
    warnungen: list[str] = []
    total = 0.0

    for pos, match in zip(anfrage.positionen, matches):
        item, warnings = _build_item(pos, match, price_overrides)
        items.append(item)
        warnungen.extend(warnings)
        total += item.gesamtpreis

    return Quotation(
        kunde_firma=anfrage.kunde_firma,
        kunde_ansprechpartner=anfrage.kunde_ansprechpartner,
        kunde_email=anfrage.kunde_email,
        belegnummer=anfrage.belegnummer,
        incoterms=anfrage.incoterms,
        zahlungsbedingungen=anfrage.zahlungsbedingungen,
        items=items,
        gesamtsumme=round(total, 2),
        waehrung="EUR",
        warnungen=warnungen,
    )


def _build_item(
    pos: Position,
    match: MatchResult,
    price_overrides: dict[str, dict[str, float]],
) -> tuple[QuotationItem, list[str]]:
    artikel_nr = match.matched_artikelnr or pos.artikelnummer or "N/A"
    bezeichnung = match.matched_bezeichnung or pos.bezeichnung

    warnings: list[str] = []
    bemerkung = ""

    if match.status == "no_match":
        bemerkung = "No master-data match - price needs manual review"
        warnings.append(f"Pos {pos.pos_nr}: no match")
    elif match.status in ("fuzzy", "semantic"):
        bemerkung = f"Uncertain match (score {match.score:.0%}) - verify"
        warnings.append(f"Pos {pos.pos_nr}: {match.status} match on {artikel_nr}")

    base_price, zkalk = _resolve_price(artikel_nr, match, price_overrides)

    # Certificates: flat surcharge, no discount, no qty multiplication
    if pos.ist_zertifikat:
        einzelpreis = base_price + zkalk
        rabatt = 0.0
        gesamtpreis = einzelpreis
        if not bemerkung:
            bemerkung = "Certificate - flat surcharge"
    else:
        rabatt = volume_discount(pos.menge)
        einzelpreis = base_price * (1 - rabatt) + zkalk
        gesamtpreis = einzelpreis * pos.menge

    return (
        QuotationItem(
            pos_nr=pos.pos_nr,
            artikel_nr=artikel_nr,
            bezeichnung=bezeichnung,
            menge=pos.menge,
            einheit=pos.einheit,
            einzelpreis=round(einzelpreis, 2),
            rabatt_prozent=round(rabatt * 100, 1),
            gesamtpreis=round(gesamtpreis, 2),
            bemerkung=bemerkung,
        ),
        warnings,
    )


def _resolve_price(
    artikel_nr: str,
    match: MatchResult,
    overrides: dict[str, dict[str, float]],
) -> tuple[float, float]:
    """Return (base_price, zkalk_offset). Overrides win over master-data."""
    if artikel_nr in overrides:
        o = overrides[artikel_nr]
        return o["basispreis"], o["zkalk_offset"]
    if match.matched_row:
        row = match.matched_row
        try:
            return (
                float(row.get("basispreis_eur", 0) or 0),
                float(row.get("zkalk_offset_eur", 0) or 0),
            )
        except ValueError:
            return 0.0, 0.0
    return 0.0, 0.0
