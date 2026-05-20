from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from quoting.api.approval_store import ApprovalRecord
from quoting.api.services.quotation_service import (
    filter_redundant_custom_price_overrides,
)
from quoting.api.services.review_service import ReviewDataService
from quoting.api.settings_store import AppSettings
from quoting.api.use_cases.errors import UseCaseUnprocessable
from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.pipeline import QuotingPipeline
from quoting.pricing import Quotation
from quoting.reviews import api_base_url, draft_pdf_filename, final_pdf_filename
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.services.quality_gate_service import QualityGateResult

log = logging.getLogger("quoting.frontend_router")

ReviewDataLoader = Callable[
    [str, QuotingPipeline],
    tuple[Anfrage, list[MatchResult], list[dict]],
]
QuotationBuilder = Callable[[Anfrage, list, list, Path, str], Quotation]
QualityGateEvaluator = Callable[
    [Anfrage, list[MatchResult], Quotation | None, list[dict] | None],
    "QualityGateResult",
]
PdfBuilder = Callable[..., None]
SettingsLoader = Callable[[], AppSettings]
ApprovalTransition = Callable[..., ApprovalRecord]


def build_review_response(
    review_id: str,
    *,
    status: str,
    review_ui_base_url: str,
) -> dict:
    base = api_base_url()
    return {
        "review_id": review_id,
        "review_url": f"{review_ui_base_url}?review_id={review_id}",
        "draft_pdf_url": f"{base}/api/reviews/{review_id}/pdf/draft",
        "draft_pdf_filename": draft_pdf_filename(review_id),
        "final_pdf_url": f"{base}/api/reviews/{review_id}/pdf/final",
        "final_pdf_filename": final_pdf_filename(review_id),
        "status_url": f"{base}/api/reviews/{review_id}/status",
        "approval_url": f"{base}/api/reviews/{review_id}/approval",
        "status": status,
    }


def format_mail_dict(mail_meta: dict) -> dict:
    return {
        "subject": str(mail_meta.get("subject") or ""),
        "from": str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        "body": str(mail_meta.get("body") or ""),
        "attachments": list(mail_meta.get("attachments") or []),
    }


def review_dir(repo: SQLiteReviewRepository, review_id: str) -> Path:
    folder = repo.artifact_dir(review_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_review_data_for_use_case(
    review_id: str,
    *,
    pipeline: QuotingPipeline,
    repo: SQLiteReviewRepository,
    review_data: ReviewDataService,
    review_data_loader: ReviewDataLoader | None,
) -> tuple[Anfrage, list[MatchResult], list[dict]]:
    if review_data_loader is not None:
        return review_data_loader(review_id, pipeline)
    try:
        anfrage = review_data.load_or_extract_anfrage(review_id, pipeline)
    except Exception as exc:
        log.exception("load_review_data: anfrage load failed for %s", review_id)
        raise UseCaseUnprocessable(
            f"Anfrage konnte nicht geladen werden: {exc}"
        ) from exc

    try:
        matches = review_data.load_or_recompute_matches(review_id, anfrage, pipeline)
    except Exception as exc:
        log.exception("load_review_data: match recompute failed for %s", review_id)
        raise UseCaseUnprocessable(f"Matching fehlgeschlagen: {exc}") from exc

    overrides = repo.load_overrides(review_id)
    overrides = filter_redundant_custom_price_overrides(overrides, matches)
    return anfrage, matches, overrides
