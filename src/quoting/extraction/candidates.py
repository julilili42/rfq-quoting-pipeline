"""Cheap local source hints for the LLM extraction prompt."""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
_ARTICLE_RE = re.compile(r"\b(?=[A-Z0-9./-]{7,}\b)(?=[A-Z0-9./-]*\d)(?=[A-Z0-9./-]*[A-Z])[A-Z0-9][A-Z0-9./-]{6,}\b")

_LABELED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "belegnummer",
        re.compile(
            r"\b(?:Beleg(?:nummer|-Nr\.?)|Anfrage\s*/\s*Beleg-?Nr\.?|Anfrage-?Nr\.?|RFQ(?:\s*No\.?)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]{3,})",
            re.I,
        ),
    ),
    (
        "kundennummer",
        re.compile(
            r"\b(?:Kunden(?:nummer|-Nr\.?)|Kd\.?-?Nr\.?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]{2,})",
            re.I,
        ),
    ),
    (
        "kontakt",
        re.compile(
            r"\b(?:Ansprechpartner|Bearbeiter)\b\s*[:#-]?\s*([A-ZÄÖÜ][A-ZÄÖÜa-zäöüß.-]+(?:\s+[A-ZÄÖÜ][A-ZÄÖÜa-zäöüß.-]+){0,3})",
            re.I,
        ),
    ),
)


def build_candidate_hints(mail_body: str, doc_sections: list[str]) -> str:
    """Return compact, non-authoritative extraction hints.

    The hints are derived with fast regexes from text already available before
    the LLM call. They are intentionally short so they reduce ambiguity without
    adding meaningful prompt latency.
    """
    source_text = "\n".join([mail_body, *doc_sections])
    lines: list[str] = [
        "These are local regex hints from the source text. They may be incomplete.",
        "Prefer hinted exact values for emails, dates, document numbers, customer numbers and article numbers when source evidence supports them.",
        "Do not invent values outside the source text.",
    ]

    labeled_lines = []
    for label, pattern in _LABELED_PATTERNS:
        values = _unique(_clean_value(v) for v in pattern.findall(source_text))
        if values:
            labeled_lines.append(f"{label}: {', '.join(values[:8])}")
    if labeled_lines:
        lines.append("labeled values: " + " | ".join(labeled_lines))

    emails = _unique(_EMAIL_RE.findall(source_text))
    if emails:
        lines.append("emails: " + ", ".join(emails[:10]))

    dates = _unique(_DATE_RE.findall(source_text))
    if dates:
        lines.append("dates: " + ", ".join(dates[:10]))

    article_numbers = _unique(
        token
        for token in _ARTICLE_RE.findall(source_text.upper())
        if not token.startswith(("HTTP", "WWW")) and "@" not in token
    )
    if article_numbers:
        lines.append("article-number-like tokens: " + ", ".join(article_numbers[:25]))

    return "\n".join(lines) if len(lines) > 3 else ""


def _clean_value(value: str) -> str:
    return re.split(r"\s{2,}|\t|\|", value.strip(), maxsplit=1)[0].strip(" :#-")


def _unique(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
