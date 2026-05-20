from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quoting.api.services.quotation_service import (
    filter_redundant_custom_price_overrides,
)
from quoting.api.services.review_service import ReviewDataService
from quoting.api.use_cases.common import format_mail_dict
from quoting.pipeline import QuotingPipeline
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.services.review_read_service import ReviewReadService


@dataclass
class GetReviewDetailUseCase:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    review_data: ReviewDataService
    review_reads: ReviewReadService

    def execute(self, review_id: str) -> dict:
        anfrage = self.review_data.load_or_extract_anfrage(review_id, self.pipeline)
        original_anfrage = self.review_data.try_load_original_anfrage(review_id) or anfrage
        matches = self.review_data.load_or_recompute_matches(
            review_id,
            anfrage,
            self.pipeline,
        )
        quotation = self.review_reads.load_saved_quotation(review_id)

        overrides = self.repo.load_overrides(review_id)
        overrides = filter_redundant_custom_price_overrides(overrides, matches)

        mail_meta = self.repo.load_mail(review_id) or {}
        progress = self.repo.load_progress(review_id) or {}

        return {
            "review_id": review_id,
            "created_at": progress.get("created_at"),
            "anfrage": anfrage.model_dump(mode="json"),
            "original_anfrage": original_anfrage.model_dump(mode="json"),
            "matches": [m.to_dict() for m in matches],
            "quotation": quotation.to_dict() if quotation else None,
            "manual_overrides": overrides,
            "mail": format_mail_dict(mail_meta),
            "has_draft_pdf": self.review_reads.find_draft_pdf(review_id) is not None,
            "has_final_pdf": self.review_reads.find_final_pdf(review_id) is not None,
        }
