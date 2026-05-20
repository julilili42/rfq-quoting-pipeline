"""Manual commercial overrides for generated quotations.

This module belongs to the pricing domain. The old Streamlit review agent
still parses free-text instructions, but applying those parsed instructions to
quotation numbers should not depend on any UI package.
"""
from __future__ import annotations

from copy import deepcopy

from quoting.core import Anfrage

from .quotation import Quotation


def _t(lang: str, key: str) -> str:
    de = {
        "manual_discount_note": "Manueller Rabatt: -{pct:.1f}%",
        "manual_price_note": "Manueller Preis: {price:.2f} EUR",
        "manual_total_note": "Manueller Gesamtpreis: {price:.2f} EUR",
        "manual_adjustments_warning": "Manuelle Agent-Anpassungen auf {count} Position(en) angewendet.",
    }
    en = {
        "manual_discount_note": "Manual discount: -{pct:.1f}%",
        "manual_price_note": "Manual price: {price:.2f} EUR",
        "manual_total_note": "Manual total price: {price:.2f} EUR",
        "manual_adjustments_warning": "Manual agent adjustments applied to {count} item(s).",
    }
    table = {"de": de, "en": en}.get(lang, de)
    return table[key]


def upsert_override(overrides: list[dict], new_override: dict) -> list[dict]:
    """Replace an existing override for the same target, or append a new one."""
    merged = []
    replaced = False

    for item in overrides:
        same_pos = (
            item.get("target") == "pos"
            and new_override.get("target") == "pos"
            and item.get("pos_nr") == new_override.get("pos_nr")
        )
        same_art = (
            item.get("target") == "artikel"
            and new_override.get("target") == "artikel"
            and item.get("artikel_nr") == new_override.get("artikel_nr")
        )

        if same_pos or same_art:
            merged.append(new_override)
            replaced = True
        else:
            merged.append(item)

    if not replaced:
        merged.append(new_override)

    return merged


def apply_manual_overrides(
    base_quotation: Quotation,
    anfrage: Anfrage,
    overrides: list[dict],
    lang: str = "de",
) -> tuple[Quotation, int]:
    """Apply manual price/discount overrides to a quotation copy."""
    quotation = deepcopy(base_quotation)
    if not overrides:
        return quotation, 0

    cert_by_pos = {pos.pos_nr: pos.ist_zertifikat for pos in anfrage.positionen}
    by_pos_total = {
        int(x["pos_nr"]): float(x["total_price_eur"])
        for x in overrides
        if x.get("target") == "pos"
        and x.get("mode") == "total_price_eur"
        and "pos_nr" in x
        and "total_price_eur" in x
    }
    by_art_total = {
        str(x["artikel_nr"]): float(x["total_price_eur"])
        for x in overrides
        if x.get("target") == "artikel"
        and x.get("mode") == "total_price_eur"
        and "artikel_nr" in x
        and "total_price_eur" in x
    }
    by_pos_price = {
        int(x["pos_nr"]): float(x["unit_price_eur"])
        for x in overrides
        if x.get("target") == "pos"
        and x.get("mode") == "unit_price_eur"
        and "pos_nr" in x
        and "unit_price_eur" in x
    }
    by_art_price = {
        str(x["artikel_nr"]): float(x["unit_price_eur"])
        for x in overrides
        if x.get("target") == "artikel"
        and x.get("mode") == "unit_price_eur"
        and "artikel_nr" in x
        and "unit_price_eur" in x
    }
    by_pos = {
        int(x["pos_nr"]): float(x["discount_pct"])
        for x in overrides
        if x.get("target") == "pos"
        and x.get("mode", "discount_pct") == "discount_pct"
        and "pos_nr" in x
        and "discount_pct" in x
    }
    by_art = {
        str(x["artikel_nr"]): float(x["discount_pct"])
        for x in overrides
        if x.get("target") == "artikel"
        and x.get("mode", "discount_pct") == "discount_pct"
        and "artikel_nr" in x
        and "discount_pct" in x
    }

    disable_vol_disc = {
        int(x["pos_nr"])
        for x in overrides
        if x.get("target") == "pos"
        and x.get("mode") == "disable_volume_discount"
        and "pos_nr" in x
    }

    applied = 0
    for item in quotation.items:
        is_certificate = bool(cert_by_pos.get(item.pos_nr, False))

        if item.pos_nr in disable_vol_disc and item.rabatt_prozent > 0 and not is_certificate:
            rabatt_fraction = item.rabatt_prozent / 100.0
            item.einzelpreis = round(item.einzelpreis + item.basispreis_eur * rabatt_fraction, 2)
            item.gesamtpreis = round(item.einzelpreis * item.menge, 2)
            item.rabatt_prozent = 0.0
            applied += 1

        fixed_total = None
        if item.pos_nr in by_pos_total:
            fixed_total = by_pos_total[item.pos_nr]
        elif item.artikel_nr in by_art_total:
            fixed_total = by_art_total[item.artikel_nr]

        if fixed_total is not None:
            item.gesamtpreis = round(max(0.0, fixed_total), 2)
            if is_certificate:
                item.einzelpreis = item.gesamtpreis
            else:
                item.einzelpreis = round(item.gesamtpreis / item.menge, 2) if item.menge else 0.0
            item.rabatt_prozent = 0.0
            note = _t(lang, "manual_total_note").format(price=item.gesamtpreis)
            item.bemerkung = f"{item.bemerkung}; {note}" if item.bemerkung else note
            applied += 1
            continue

        fixed_price = None
        if item.pos_nr in by_pos_price:
            fixed_price = by_pos_price[item.pos_nr]
        elif item.artikel_nr in by_art_price:
            fixed_price = by_art_price[item.artikel_nr]

        if fixed_price is not None:
            item.einzelpreis = round(max(0.0, fixed_price), 2)
            item.gesamtpreis = (
                item.einzelpreis
                if is_certificate
                else round(item.einzelpreis * item.menge, 2)
            )
            item.rabatt_prozent = 0.0
            note = _t(lang, "manual_price_note").format(price=item.einzelpreis)
            item.bemerkung = f"{item.bemerkung}; {note}" if item.bemerkung else note
            applied += 1
            continue

        extra_discount = None
        if item.pos_nr in by_pos:
            extra_discount = by_pos[item.pos_nr]
        elif item.artikel_nr in by_art:
            extra_discount = by_art[item.artikel_nr]

        if extra_discount is None:
            continue

        new_unit = round(item.einzelpreis * (1 - extra_discount / 100.0), 2)
        new_total = new_unit if is_certificate else round(new_unit * item.menge, 2)

        item.einzelpreis = new_unit
        item.gesamtpreis = round(new_total, 2)
        item.rabatt_prozent = round(min(100.0, item.rabatt_prozent + extra_discount), 1)

        note = _t(lang, "manual_discount_note").format(pct=extra_discount)
        item.bemerkung = f"{item.bemerkung}; {note}" if item.bemerkung else note
        applied += 1

    quotation.gesamtsumme = round(sum(it.gesamtpreis for it in quotation.items), 2)
    if applied:
        quotation.warnungen.append(
            _t(lang, "manual_adjustments_warning").format(count=applied)
        )
    return quotation, applied
