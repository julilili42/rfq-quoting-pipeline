"""Application service for review workflows.

The routers should stay thin HTTP adapters. This module owns the orchestration
for review-detail loading and user-driven mutations such as editing positions,
regenerating the draft PDF, and finalizing a quotation.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException

from quoting.api.approval_store import (
    VALID_TRANSITIONS,
    ApprovalRecord,
    ApprovalState,
    ApprovalStore,
)
from quoting.api.progress_store import ProgressStore
from quoting.api.services.quality_gate_service import (
    QualityGateResult,
    evaluate_quality_gate,
)
from quoting.api.services.quotation_service import (
    build_quotation_with_overrides,
    filter_redundant_custom_price_overrides,
)
from quoting.api.services.review_read_service import ReviewReadService
from quoting.api.services.review_service import ReviewDataService
from quoting.api.settings_store import AppSettings, load_user_settings
from quoting.api.use_cases.dtos import IncomingMailReview
from quoting.api.use_cases.review_workflow import (
    CreateReviewFromMailUseCase,
    DeleteReviewUseCase,
    FinalizeQuotationUseCase,
    GetReviewDetailUseCase,
    RegenerateQuotationUseCase,
    ResetReviewUseCase,
    SaveOverridesUseCase,
    UpdateAnfrageUseCase,
    format_mail_dict,
)
from quoting.api.use_cases.review_workflow import (
    build_review_response as build_review_response_payload,
)
from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline
from quoting.pricing import Quotation
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.pipeline_coordinator import PipelineCoordinator

log = logging.getLogger("quoting.frontend_router")

ReviewDataLoader = Callable[
    [str, QuotingPipeline],
    tuple[Anfrage, list[MatchResult], list[dict]],
]
QuotationBuilder = Callable[[Anfrage, list, list, Path, str], Quotation]
QualityGateEvaluator = Callable[..., QualityGateResult]
PdfBuilder = Callable[..., None]
SettingsLoader = Callable[[], AppSettings]
ApprovalTransition = Callable[..., ApprovalRecord]


def load_review_data(
    review_id: str,
    pipeline: QuotingPipeline,
    *,
    repo: SQLiteReviewRepository,
    review_data_service: ReviewDataService | None = None,
) -> tuple[Anfrage, list[MatchResult], list[dict]]:
    """Load anfrage, matches, and overrides for a review."""
    data_service = review_data_service or ReviewDataService(repo)
    try:
        anfrage = data_service.load_or_extract_anfrage(review_id, pipeline)
    except Exception as exc:
        log.exception("load_review_data: anfrage load failed for %s", review_id)
        raise HTTPException(422, f"Anfrage konnte nicht geladen werden: {exc}") from exc

    try:
        matches = data_service.load_or_recompute_matches(review_id, anfrage, pipeline)
    except Exception as exc:
        log.exception("load_review_data: match recompute failed for %s", review_id)
        raise HTTPException(422, f"Matching fehlgeschlagen: {exc}") from exc

    overrides = repo.load_overrides(review_id)
    overrides = filter_redundant_custom_price_overrides(overrides, matches)
    return anfrage, matches, overrides


@dataclass
class ReviewWorkflowService:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    review_ui_base_url: str = "http://localhost:8501"
    settings_loader: SettingsLoader = load_user_settings
    review_data_loader: ReviewDataLoader | None = None
    quotation_builder: QuotationBuilder = build_quotation_with_overrides
    quality_gate_evaluator: QualityGateEvaluator = evaluate_quality_gate
    pdf_builder: PdfBuilder = build_draft_pdf
    approval_store: ApprovalStore | None = None
    progress_store: ProgressStore | None = None
    review_data: ReviewDataService | None = None
    review_read_service: ReviewReadService | None = None
    approval_transition: ApprovalTransition | None = None
    coordinator: PipelineCoordinator | None = None

    @property
    def approvals(self) -> ApprovalStore:
        if self.approval_store is None:
            self.approval_store = ApprovalStore(self.repo)
        return self.approval_store

    @property
    def progress_store_for_review(self) -> ProgressStore:
        if self.progress_store is None:
            self.progress_store = ProgressStore(self.repo)
        return self.progress_store

    @property
    def review_data_service(self) -> ReviewDataService:
        if self.review_data is None:
            self.review_data = ReviewDataService(
                self.repo,
                approval_store=self.approvals,
            )
        return self.review_data

    @property
    def review_reads(self) -> ReviewReadService:
        if self.review_read_service is None:
            self.review_read_service = ReviewReadService(self.repo)
        return self.review_read_service

    def _require_coordinator(self) -> PipelineCoordinator:
        """Return the configured coordinator or fail loudly.

        The container is expected to wire the coordinator before any
        request handler is reached. Tests that don't exercise the
        pipeline-creation path can leave it unset.
        """
        if self.coordinator is None:
            raise RuntimeError(
                "ReviewWorkflowService has no PipelineCoordinator configured — "
                "the JobWorker lifespan must initialise one at app startup."
            )
        return self.coordinator

    def create_review_from_mail(
        self,
        payload: IncomingMailReview,
    ) -> dict:
        return CreateReviewFromMailUseCase(
            repo=self.repo,
            progress_store=self.progress_store_for_review,
            approval_store=self.approvals,
            coordinator=self._require_coordinator(),
            review_ui_base_url=self.review_ui_base_url,
        ).execute(payload)

    def reset_review(self, review_id: str) -> dict:
        """Reset a review and re-run the pipeline against the saved mail."""
        return ResetReviewUseCase(
            repo=self.repo,
            progress_store=self.progress_store_for_review,
            approval_store=self.approvals,
            review_data=self.review_data_service,
            coordinator=self._require_coordinator(),
        ).execute(review_id)

    def get_progress(self, review_id: str) -> dict[str, Any]:
        progress = self.progress_store_for_review.read(review_id)
        if progress is None:
            raise HTTPException(404, f"Progress for review {review_id} not found")
        return progress

    def get_approval(self, review_id: str) -> dict:
        return self.approvals.load(review_id).to_dict()

    def transition_approval(
        self,
        review_id: str,
        *,
        target: str,
        actor: str | None = None,
        changed_fields: list[str] | None = None,
        warning_acknowledged: bool | None = None,
        exception_reason: str | None = None,
    ) -> dict:
        if target not in VALID_TRANSITIONS:
            raise HTTPException(400, f"Unknown target state: {target}")
        try:
            record = self.approvals.transition(
                review_id,
                target=cast(ApprovalState, target),
                actor=actor,
                changed_fields=changed_fields,
                warning_acknowledged=warning_acknowledged,
                exception_reason=exception_reason,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return record.to_dict()

    def mark_review_opened(self, review_id: str) -> dict:
        record = self.approvals.mark_opened(review_id)
        return record.to_dict()

    def get_outlook_item_status(self, outlook_item_id: str) -> dict | None:
        """Compact status payload for an Outlook-item-bound review.

        Returns the minimal view the Outlook plugin needs to render the
        right card. ``None`` when no review is bound to this item.
        """
        review = self.repo.get_review_by_outlook_item_id(outlook_item_id)
        if review is None:
            return None
        review_id = str(review["review_id"])
        approval = self.approvals.load(review_id)
        progress = self.repo.load_progress(review_id) or {}
        anfrage = self.repo.load_anfrage_reviewed(review_id) or {}
        return {
            "review_id": review_id,
            "subject": review.get("subject") or "",
            "sender": review.get("sender") or "",
            "created_at": review.get("created_at"),
            "approval_state": approval.state,
            "progress_status": progress.get("status"),
            "opened_at": approval.opened_at,
            "approved_at": approval.approved_at,
            "approved_by": approval.approved_by,
            "sent_at": approval.sent_at,
            "final_pdf_filename": approval.final_pdf_path,
            "kunden_firma": anfrage.get("kunde_firma") if isinstance(anfrage, dict) else None,
            "review_url": f"{self.review_ui_base_url}?review_id={review_id}",
        }

    def detach_outlook_item(self, outlook_item_id: str) -> dict | None:
        """Unlink any review currently bound to this Outlook item.

        The review itself is preserved (and still reachable via the
        overview). Returns the detached review_id or ``None`` if no
        review was bound.
        """
        review = self.repo.get_review_by_outlook_item_id(outlook_item_id)
        if review is None:
            return None
        review_id = str(review["review_id"])
        self.repo.set_outlook_item_id(review_id, None)
        return {"review_id": review_id}

    def build_review_response(self, review_id: str, *, status: str) -> dict:
        return build_review_response_payload(
            review_id,
            status=status,
            review_ui_base_url=self.review_ui_base_url,
        )

    def list_reviews(self, summaries: list[Any] | None = None) -> list[dict]:
        summaries = summaries if summaries is not None else self.review_reads.scan_reviews()
        return [
            {
                "review_id": s.review_id,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "subject": s.subject,
                "sender": s.sender,
                "customer": s.customer,
                "positions": s.positions,
                "confidence_high": s.confidence_high,
                "confidence_medium": s.confidence_medium,
                "confidence_low": s.confidence_low,
                "matches_exact": s.matches_exact,
                "matches_fuzzy": s.matches_fuzzy,
                "matches_semantic": s.matches_semantic,
                "matches_no_match": s.matches_no_match,
                "total_eur": s.total_eur,
                "currency": s.currency,
                "status": s.status,
                "has_pdf": bool(s.pdf_path),
                "manual_overrides_count": s.manual_overrides_count,
                "escalation": s.escalation,
                "extracted_articles": s.extracted_articles,
            }
            for s in summaries
        ]

    def get_detail(self, review_id: str) -> dict:
        return GetReviewDetailUseCase(
            repo=self.repo,
            pipeline=self.pipeline,
            review_data=self.review_data_service,
            review_reads=self.review_reads,
        ).execute(review_id)

    def delete_review(self, review_id: str) -> None:
        DeleteReviewUseCase(repo=self.repo).execute(review_id)

    def get_mail(self, review_id: str) -> dict:
        meta = self.repo.load_mail(review_id) or {}
        return format_mail_dict(meta)

    def update_anfrage(self, review_id: str, payload: dict) -> dict:
        return UpdateAnfrageUseCase(
            repo=self.repo,
            pipeline=self.pipeline,
            review_data=self.review_data_service,
        ).execute(review_id, payload)

    def save_overrides(self, review_id: str, payload: list[dict]) -> list[dict]:
        return SaveOverridesUseCase(
            repo=self.repo,
            review_data=self.review_data_service,
        ).execute(review_id, payload)

    def regenerate_quotation(self, review_id: str, *, build_pdf: bool = True) -> dict:
        return RegenerateQuotationUseCase(
            repo=self.repo,
            pipeline=self.pipeline,
            settings_loader=self.settings_loader,
            review_data_loader=self.review_data_loader,
            review_data=self.review_data_service,
            quotation_builder=self.quotation_builder,
            pdf_builder=self.pdf_builder,
        ).execute(review_id, build_pdf=build_pdf)

    def finalize_quotation(
        self,
        review_id: str,
        *,
        actor: str,
        filename: str | None,
        warning_acknowledged: bool,
        exception_reason: str | None,
    ) -> dict:
        return FinalizeQuotationUseCase(
            repo=self.repo,
            pipeline=self.pipeline,
            settings_loader=self.settings_loader,
            review_data_loader=self.review_data_loader,
            review_data=self.review_data_service,
            quotation_builder=self.quotation_builder,
            quality_gate_evaluator=self.quality_gate_evaluator,
            pdf_builder=self.pdf_builder,
            approval_store=self.approvals,
            approval_transition=self.approval_transition,
        ).execute(
            review_id,
            actor=actor,
            filename=filename,
            warning_acknowledged=warning_acknowledged,
            exception_reason=exception_reason,
        )
