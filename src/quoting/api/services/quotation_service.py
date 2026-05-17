"""Quotation building, manual-override filtering, and final-PDF filename helpers."""

from __future__ import annotations

import logging
import re
from datetime import date as _date
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.pricing import Quotation, build_quotation
from quoting.ui.review_agent import apply_manual_overrides

log = logging.getLogger("quoting.frontend_router")


def build_quotation_with_overrides(
    anfrage: Anfrage,
    matches: list,
    overrides: list,
    preise_path: Path,
    review_id: str,
) -> Quotation:
    """Build quotation and apply manual overrides."""
    try:
        quotation = build_quotation(anfrage, matches, preise_path)
        if isinstance(overrides, list) and overrides:
            quotation, _ = apply_manual_overrides(quotation, anfrage, overrides, lang="de")
        return quotation
    except Exception as exc:
        log.exception("build_quotation_with_overrides: pricing failed for %s", review_id)
        raise HTTPException(422, f"Preisberechnung fehlgeschlagen: {exc}") from exc


def remove_position_price_overrides(
    overrides: list[dict],
    pos_nr: int,
) -> list[dict]:
    filtered = []
    for override in overrides:
        if not isinstance(override, dict):
            filtered.append(override)
            continue

        try:
            override_pos_nr = int(override.get("pos_nr") or 0)
        except (TypeError, ValueError):
            filtered.append(override)
            continue

        if (
            override.get("target") == "pos"
            and override_pos_nr == pos_nr
            and override.get("mode") in {"unit_price_eur", "total_price_eur"}
        ):
            continue

        filtered.append(override)

    return filtered


def filter_redundant_custom_price_overrides(
    overrides: list[dict],
    matches: list[MatchResult],
) -> list[dict]:
    custom_unit_price_by_pos = {}
    for match in matches:
        row = match.matched_row or {}
        if not (row.get("custom") or row.get("source") == "custom"):
            continue
        try:
            custom_unit_price_by_pos[match.pos_nr] = float(row.get("basispreis_eur") or 0)
        except (TypeError, ValueError):
            continue

    if not custom_unit_price_by_pos:
        return overrides

    filtered = []
    for override in overrides:
        if not isinstance(override, dict):
            filtered.append(override)
            continue

        if (
            override.get("target") != "pos"
            or override.get("mode") != "unit_price_eur"
        ):
            filtered.append(override)
            continue

        try:
            pos_nr = int(override.get("pos_nr") or 0)
            unit_price = float(override.get("unit_price_eur") or 0)
        except (TypeError, ValueError):
            filtered.append(override)
            continue

        custom_unit_price = custom_unit_price_by_pos.get(pos_nr)
        if custom_unit_price is not None and abs(unit_price - custom_unit_price) < 0.005:
            continue

        filtered.append(override)

    return filtered


def sanitize_pdf_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', '_', name.strip())
    name = name.replace(' ', '_')
    name = re.sub(r'_+', '_', name)
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name[:200]


def resolve_filename_template(template: str, anfrage: Any, review_id: str) -> str:
    def _field(name: str) -> str:
        return (getattr(anfrage, name, '') or '').strip()

    today = _date.today().strftime('%Y%m%d')
    result = (
        template
        .replace('[Kunde]', _field('kunde_firma') or review_id)
        .replace('[Belegnummer]', _field('belegnummer'))
        .replace('[Kundennummer]', _field('kundennummer'))

        .replace('[Ansprechpartner]', _field('kunde_ansprechpartner'))
        .replace('[Datum]', today)
    )
    return sanitize_pdf_filename(result)
