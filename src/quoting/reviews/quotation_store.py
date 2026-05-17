from __future__ import annotations

from pathlib import Path

from quoting.pricing import Quotation, QuotationItem
from quoting.reviews.store import read_json


def load_saved_quotation(review_dir: Path) -> Quotation | None:
    candidates = [
        review_dir / "quotation_reviewed.json",
        review_dir / "03_quotation.json",
        review_dir / "pipeline" / "03_quotation.json",
    ]
    candidates.extend(sorted(review_dir.rglob("03_quotation.json")))

    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)

        data = read_json(path)
        if isinstance(data, dict):
            try:
                return quotation_from_dict(data)
            except Exception:
                continue

    return None


def quotation_from_dict(data: dict) -> Quotation:
    items = [
        QuotationItem(
            pos_nr=int(item.get("pos_nr", 0)),
            artikel_nr=str(item.get("artikel_nr", "")),
            bezeichnung=str(item.get("bezeichnung", "")),
            menge=float(item.get("menge", 0) or 0),
            einheit=str(item.get("einheit", "")),
            einzelpreis=float(item.get("einzelpreis", 0) or 0),
            rabatt_prozent=float(item.get("rabatt_prozent", 0) or 0),
            gesamtpreis=float(item.get("gesamtpreis", 0) or 0),
            bemerkung=str(item.get("bemerkung", "")),
        )
        for item in data.get("items", [])
        if isinstance(item, dict)
    ]

    return Quotation(
        kunde_firma=data.get("kunde_firma"),
        kunde_ansprechpartner=data.get("kunde_ansprechpartner"),
        kunde_email=data.get("kunde_email"),
        kundennummer=data.get("kundennummer"),
        belegnummer=data.get("belegnummer"),
        incoterms=data.get("incoterms"),
        zahlungsbedingungen=data.get("zahlungsbedingungen"),
        items=items,
        gesamtsumme=float(data.get("gesamtsumme", 0) or 0),
        waehrung=str(data.get("waehrung", "EUR")),
        warnungen=list(data.get("warnungen", [])),
    )
