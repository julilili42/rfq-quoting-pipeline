"""Post-LLM source checks for extracted RFQ data."""
from __future__ import annotations

import re
import unicodedata
from math import ceil

from ..core import Anfrage, Position

_STRICT_HEADER_FIELDS = ("kunde_email", "belegnummer", "datum", "kundennummer")
_TOKEN_HEADER_FIELDS = ("kunde_ansprechpartner", "kunde_firma")
_LEGAL_FORM_TOKENS = {
    "ag",
    "co",
    "company",
    "gmbh",
    "kg",
    "ltd",
    "mbh",
    "ohg",
    "sarl",
}


def harden_extraction_with_sources(
    anfrage: Anfrage,
    mail_body: str,
    doc_sections: list[str],
) -> list[str]:
    """Downgrade or clear values that are not supported by source text.

    The guard intentionally uses only already-loaded text, so it adds no LLM
    latency. Vision-only scans still pass through: when there is no meaningful
    source text, this function does not clear values that could only be read
    from an image.
    """
    if _has_vision_input(doc_sections) and not _has_document_text(doc_sections):
        return []

    source_text = _source_text(mail_body, doc_sections)
    if not _has_meaningful_source_text(source_text):
        return []

    changes: list[str] = []
    for field in _STRICT_HEADER_FIELDS:
        value = getattr(anfrage, field)
        if value and not _value_supported(str(value), source_text):
            setattr(anfrage, field, None)
            anfrage.header_evidence.pop(field, None)
            _append_uncertainty(
                anfrage,
                f"{_label(field)} '{value}' verworfen: nicht im Quelltext belegt.",
            )
            changes.append(field)

    for field in _TOKEN_HEADER_FIELDS:
        value = getattr(anfrage, field)
        if value and not _name_or_company_supported(str(value), source_text):
            setattr(anfrage, field, None)
            anfrage.header_evidence.pop(field, None)
            _append_uncertainty(
                anfrage,
                f"{_label(field)} '{value}' verworfen: nicht im Quelltext belegt.",
            )
            changes.append(field)

    for pos in anfrage.positionen:
        changes.extend(_harden_position(anfrage, pos, source_text))

    return changes


def _harden_position(anfrage: Anfrage, pos: Position, source_text: str) -> list[str]:
    changes: list[str] = []
    article_supported = _value_supported(pos.artikelnummer, source_text)
    quote_supported = bool(pos.source_quote and _quote_supported(pos.source_quote, source_text))

    if not article_supported and not quote_supported:
        if pos.confidence != "low":
            pos.confidence = "low"
            changes.append(f"position:{pos.pos_nr}:confidence")
        _append_uncertainty(
            anfrage,
            f"Pos {pos.pos_nr}: Artikelnummer '{pos.artikelnummer}' nicht im Quelltext belegt.",
        )

    if pos.menge <= 0:
        if pos.confidence != "low":
            pos.confidence = "low"
            changes.append(f"position:{pos.pos_nr}:menge")
        _append_uncertainty(
            anfrage,
            f"Pos {pos.pos_nr}: Menge fehlt oder ist 0; bitte prüfen.",
        )

    if len(pos.source_quote) > 120:
        pos.source_quote = pos.source_quote[:117].rstrip() + "..."
        changes.append(f"position:{pos.pos_nr}:source_quote")

    return changes


def _source_text(mail_body: str, doc_sections: list[str]) -> str:
    lines: list[str] = []
    if mail_body.strip():
        lines.append(mail_body)
    for section in doc_sections:
        for line in section.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("==="):
                continue
            if re.match(r"^Image \d+:", stripped):
                continue
            lines.append(stripped)
    return "\n".join(lines)


def _has_vision_input(doc_sections: list[str]) -> bool:
    return any("=== IMAGE ORDER (VISION INPUTS) ===" in section for section in doc_sections)


def _has_document_text(doc_sections: list[str]) -> bool:
    return any(
        section.startswith(("=== PDF TEXT:", "=== EXCEL:", "=== CSV:"))
        for section in doc_sections
    )


def _has_meaningful_source_text(source_text: str) -> bool:
    return len(re.findall(r"[A-Za-zÄÖÜäöüß0-9]", source_text)) >= 20


def _value_supported(value: str, source_text: str) -> bool:
    if not value.strip():
        return True
    return _compact(value) in _compact(source_text)


def _quote_supported(quote: str, source_text: str) -> bool:
    compact_quote = _compact(quote)
    if not compact_quote:
        return False
    if compact_quote in _compact(source_text):
        return True
    tokens = [token for token in _tokens(quote) if len(token) >= 4]
    if not tokens:
        return False
    source = set(_tokens(source_text))
    return sum(1 for token in tokens if token in source) >= max(1, ceil(len(tokens) * 0.8))


def _name_or_company_supported(value: str, source_text: str) -> bool:
    if _value_supported(value, source_text):
        return True
    tokens = [
        token
        for token in _tokens(value)
        if len(token) > 1 and token not in _LEGAL_FORM_TOKENS
    ]
    if not tokens:
        return True
    source_tokens = set(_tokens(source_text))
    return all(token in source_tokens for token in tokens)


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalise(value))


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _normalise(value))


def _normalise(value: str) -> str:
    value = value.casefold()
    value = (
        value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value


def _append_uncertainty(anfrage: Anfrage, message: str) -> None:
    if message not in anfrage.unsicherheiten:
        anfrage.unsicherheiten.append(message)


def _label(field: str) -> str:
    return {
        "belegnummer": "Belegnummer",
        "datum": "Datum",
        "kunde_ansprechpartner": "Ansprechpartner",
        "kunde_email": "E-Mail",
        "kunde_firma": "Firma",
        "kundennummer": "Kunden-Nr.",
    }.get(field, field)
