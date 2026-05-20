from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quoting.api.approval_store import ApprovalStore
from quoting.api.progress_store import ProgressStore
from quoting.api.services.review_service import ReviewDataService
from quoting.api.use_cases.errors import UseCaseBadRequest
from quoting.ingestion import Mail
from quoting.reviews import api_base_url, reset_review_artifacts
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.pipeline_coordinator import PipelineCoordinator


@dataclass
class ResetReviewUseCase:
    repo: SQLiteReviewRepository
    progress_store: ProgressStore
    approval_store: ApprovalStore
    review_data: ReviewDataService
    coordinator: PipelineCoordinator

    def execute(self, review_id: str) -> dict:
        reset_review_artifacts(
            review_id,
            repo=self.repo,
            progress_store=self.progress_store,
            approval_store=self.approval_store,
        )
        self._rehydrate_mail(review_id)
        self.coordinator.start_pipeline(review_id)

        base = api_base_url()
        return {
            "review_id": review_id,
            "status": "running",
            "status_url": f"{base}/api/reviews/{review_id}/status",
        }

    def _rehydrate_mail(self, review_id: str) -> Mail:
        meta = self.repo.load_mail(review_id)
        if meta is None:
            raise UseCaseBadRequest("No persisted mail payload — review cannot be reset")

        mail = self.review_data.mail_from_meta(meta, review_id)
        if not mail.has_content:
            raise UseCaseBadRequest(
                "Reset failed: mail has no body and no registered attachments.",
            )
        return mail
