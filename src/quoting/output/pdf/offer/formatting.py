"""Formatting helpers for offer PDFs."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .config import OfferPdfConfig


def html_escape(value: Any) -> str:
    """Escape text for ReportLab Paragraph HTML."""
    if value is None:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    return escape(text).replace("\n", "<br/>")


def format_qty(value: float) -> str:
    """Format quantity in German style."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html_escape(value)

    if number.is_integer():
        return str(int(number))

    formatted = f"{number:,.3f}".rstrip("0").rstrip(".")
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_eur_de(value: float) -> str:
    """Format currency amount in German style without EUR suffix."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0

    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def find_logo_path(config: OfferPdfConfig) -> Path | None:
    """Return logo path if available."""
    quoting_root = Path(__file__).resolve().parents[3]
    candidate = quoting_root / config.logo_relative_path
    return candidate if candidate.exists() else None
