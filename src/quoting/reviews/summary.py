"""Build dashboard summaries from SQLite review state."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from quoting.reviews.pdfs import find_draft_pdf
from quoting.reviews.sqlite_repository import SQLiteReviewRepository, get_default_repository

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
    customer: str
    """Best customer label for the overview. Extracted ``kunde_firma`` (then
    contact / email), independent of how the review was ingested. Empty when
    nothing was extracted — the UI falls back to ``sender``."""

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
    escalation: dict | None

    extracted_articles: list[str]
    """Article numbers extracted from the original RFQ — for top-N stats."""

    @property
    def matched(self) -> int:
        return self.matches_exact + self.matches_fuzzy + self.matches_semantic

    @property
    def match_rate(self) -> float:
        return self.matched / self.positions if self.positions else 0.0


def scan_reviews(
    *,
    repo: SQLiteReviewRepository | None = None,
) -> list[ReviewSummary]:
    """Return all review summaries from SQLite, newest first."""
    active_repo = repo or get_default_repository()
    summaries: list[ReviewSummary] = []
    for row in active_repo.list_reviews():
        review_id = str(row["review_id"])
        try:
            summaries.append(_summarize(review_id, row, repo=active_repo))
        except Exception as exc:
            log.warning("Skipping malformed review %s: %s", review_id, exc)
            continue
    return summaries


def _summarize(
    review_id: str,
    row: dict,
    *,
    repo: SQLiteReviewRepository,
) -> ReviewSummary:
    mail = repo.load_mail(review_id) or {}
    extraction = repo.load_anfrage(review_id) or {}
    reviewed = repo.load_anfrage_reviewed(review_id) or {}
    quotation = repo.load_quotation(review_id) or {}
    approval = repo.load_approval(review_id) or {}
    escalation = repo.load_escalation(review_id)
    overrides = repo.load_overrides(review_id)

    positions = extraction.get("positionen") or []
    if not isinstance(positions, list):
        positions = []

    matches = repo.load_matches(review_id)

    confidence_counts = _count_by_key(positions, "confidence", ("high", "medium", "low"))
    match_counts = _count_by_key(
        matches, "status", ("exact", "fuzzy", "semantic", "no_match")
    )
    pdf_path = find_draft_pdf(review_id, repo=repo)

    approval_state = approval.get("state") or row.get("approval_state")
    if approval_state in {"approved", "ready_to_send"}:
        status: ReviewStatus = "abgeschlossen"
    elif pdf_path:
        status = "pdf_bereit"
    else:
        status = "in_arbeit"

    extracted_articles = [
        str(p.get("artikelnummer") or "").strip()
        for p in positions
        if isinstance(p, dict) and p.get("artikelnummer")
    ]

    return ReviewSummary(
        review_id=review_id,
        folder=repo.artifact_dir(review_id),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
        subject=str(mail.get("subject") or row.get("subject") or "(ohne Betreff)"),
        sender=str(mail.get("from") or mail.get("sender") or row.get("sender") or ""),
        customer=_customer_label(reviewed) or _customer_label(extraction),
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
        manual_overrides_count=len(overrides),
        escalation=escalation if escalation and escalation.get("escalated") else None,
        extracted_articles=extracted_articles,
    )


def _customer_label(anfrage: dict) -> str:
    """First non-empty customer identity from an extracted/reviewed Anfrage."""
    for key in ("kunde_firma", "kunde_ansprechpartner", "kunde_email"):
        value = anfrage.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _count_by_key(items: list, key: str, expected: tuple[str, ...]) -> dict[str, int]:
    counts = {k: 0 for k in expected}
    for it in items:
        if not isinstance(it, dict):
            continue
        value = it.get(key)
        if value in counts:
            counts[value] += 1
    return counts


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.fromtimestamp(0)
