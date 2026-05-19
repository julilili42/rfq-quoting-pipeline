from __future__ import annotations

from quoting.pricing import Quotation, QuotationItem
from quoting.reviews.sqlite_repository import get_default_repository


def load_saved_quotation(review_id: str) -> Quotation | None:
    data = get_default_repository().load_quotation(review_id)
    if not isinstance(data, dict):
        return None
    try:
        return quotation_from_dict(data)
    except Exception:
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
