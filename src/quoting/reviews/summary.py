"""Scan ``data/reviews/`` and produce summaries for the dashboard.

The dashboard reads from disk only — it does not re-run any pipeline.
Every review folder is treated as a self-contained artifact.

Status detection
----------------
- ``abgeschlossen`` — the review was explicitly approved
  (``approval.json`` is ``approved`` or ``ready_to_send``).
- ``pdf_bereit``   — the initial pipeline has produced a draft PDF, but
  the review has not been approved yet.
- ``in_arbeit``    — the folder exists but no PDF was produced (likely a
  running or failed pipeline run).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from quoting.reviews import find_draft_pdf, read_json

log = logging.getLogger(__name__)


ReviewStatus = Literal["abgeschlossen", "pdf_bereit", "in_arbeit"]


@dataclass(frozen=True)
class ReviewSummary:
    review_id: str
    folder: Path
    created_at: datetime
    updated_at: datetime
    subject: str
    sender: str

    positions: int
    confidence_high: int
    confidence_medium: int
    confidence_low: int

    matches_exact: int
    matches_fuzzy: int
    matches_semantic: int
    matches_no_match: int

    total_eur: float
    currency: str

    status: ReviewStatus
    pdf_path: Path | None
    manual_overrides_count: int

    extracted_articles: list[str]
    """Article numbers extracted from the original RFQ — for top-N stats."""

    @property
    def matched(self) -> int:
        return (
            self.matches_exact
            + self.matches_fuzzy
            + self.matches_semantic
        )

    @property
    def match_rate(self) -> float:
        return self.matched / self.positions if self.positions else 0.0


# --------------------------------------------------------------------- public
def scan_reviews(reviews_root: Path) -> list[ReviewSummary]:
    """Return all review summaries on disk, newest first.

    Folders that fail to summarize are silently skipped — the dashboard
    should never crash because of one bad folder.
    """
    if not reviews_root.exists():
        return []

    summaries: list[ReviewSummary] = []
    for entry in reviews_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            summaries.append(_summarize(entry))
        except Exception as exc:
            log.warning("Skipping malformed review folder %s: %s", entry.name, exc)
            continue

    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


# --------------------------------------------------------------------- internal
def _summarize(folder: Path) -> ReviewSummary:
    review_id = folder.name

    mail = read_json(folder / "mail.json") or {}
    extraction = _read_json_first(folder, ("anfrage_reviewed.json",
                                           "01_extracted.json")) or {}
    quotation = _read_json_first(folder, ("quotation_reviewed.json",
                                          "03_quotation.json")) or {}
    legacy_state = read_json(folder / "review_state.json")
    approval = read_json(folder / "approval.json") or {}
    overrides = read_json(folder / "manual_overrides.json") or []

    positions = extraction.get("positionen") or []
    if not isinstance(positions, list):
        positions = []

    matches = _read_json_first(folder, ("matches_reviewed.json",
                                        "02_matches.json")) or []

    confidence_counts = _count_by_key(positions, "confidence", ("high", "medium", "low"))
    match_counts = _count_by_key(
        matches, "status", ("exact", "fuzzy", "semantic", "no_match")
    )

    pdf_path = find_draft_pdf(folder, review_id)

    approval_state = approval.get("state") if isinstance(approval, dict) else None
    has_legacy_completed_state = (
        approval_state is None
        and isinstance(legacy_state, dict)
        and "review_id" in legacy_state
    )

    if approval_state in {"approved", "ready_to_send"} or has_legacy_completed_state:
        status: ReviewStatus = "abgeschlossen"
    elif pdf_path:
        status = "pdf_bereit"
    else:
        status = "in_arbeit"

    created = _safe_mtime(folder / "mail.json" if mail else folder)
    updated = _safe_mtime(folder)

    extracted_articles = [
        str(p.get("artikelnummer") or "").strip()
        for p in positions
        if isinstance(p, dict) and p.get("artikelnummer")
    ]

    return ReviewSummary(
        review_id=review_id,
        folder=folder,
        created_at=created,
        updated_at=updated,
        subject=str(mail.get("subject") or "(ohne Betreff)"),
        sender=str(mail.get("from") or mail.get("sender") or ""),
        positions=len(positions),
        confidence_high=confidence_counts["high"],
        confidence_medium=confidence_counts["medium"],
        confidence_low=confidence_counts["low"],
        matches_exact=match_counts["exact"],
        matches_fuzzy=match_counts["fuzzy"],
        matches_semantic=match_counts["semantic"],
        matches_no_match=match_counts["no_match"],
        total_eur=float(quotation.get("gesamtsumme") or 0.0),
        currency=str(quotation.get("waehrung") or "EUR"),
        status=status,
        pdf_path=pdf_path,
        manual_overrides_count=len(overrides) if isinstance(overrides, list) else 0,
        extracted_articles=extracted_articles,
    )


def _read_json_first(folder: Path, names: tuple[str, ...]) -> Any:
    """Try ``folder/name`` for each name, then rglob as last resort."""
    for name in names:
        data = read_json(folder / name)
        if data is not None:
            return data
        # also accept nested under pipeline/
        data = read_json(folder / "pipeline" / name)
        if data is not None:
            return data

    for name in names:
        for path in folder.rglob(name):
            data = read_json(path)
            if data is not None:
                return data

    return None


def _count_by_key(items: list, key: str, expected: tuple[str, ...]) -> dict[str, int]:
    counts = {k: 0 for k in expected}
    for it in items:
        if not isinstance(it, dict):
            continue
        value = it.get(key)
        if value in counts:
            counts[value] += 1
    return counts


def _safe_mtime(path: Path | None) -> datetime:
    if path is None or not path.exists():
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return datetime.fromtimestamp(0)
