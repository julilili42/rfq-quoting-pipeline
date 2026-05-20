"""Small application dependency container for the API layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from quoting.pipeline import QuotingPipeline
from quoting.reviews.sqlite_repository import SQLiteReviewRepository, get_default_repository

if TYPE_CHECKING:
    from quoting.api.approval_store import ApprovalStore
    from quoting.api.job_queue import JobQueue
    from quoting.api.pipeline_coordinator import PipelineCoordinator
    from quoting.api.progress_store import ProgressStore
    from quoting.api.services.review_read_service import ReviewReadService
    from quoting.api.services.review_service import ReviewDataService
    from quoting.api.services.review_workflow_service import (
        ApprovalTransition,
        PdfBuilder,
        QualityGateEvaluator,
        QuotationBuilder,
        ReviewDataLoader,
        ReviewWorkflowService,
        SettingsLoader,
    )
    from quoting.api.step_handlers import StepHandlers


@dataclass
class AppContainer:
    """Lazily owns long-lived API dependencies."""

    _pipeline: QuotingPipeline | None = None
    _job_queue: JobQueue | None = None
    _step_handlers: StepHandlers | None = None
    _pipeline_coordinator: PipelineCoordinator | None = None

    def pipeline(self) -> QuotingPipeline:
        if self._pipeline is None:
            self._pipeline = QuotingPipeline()
        return self._pipeline

    def review_repo(self) -> SQLiteReviewRepository:
        return get_default_repository()

    def approval_store(
        self,
        repo: SQLiteReviewRepository | None = None,
    ) -> ApprovalStore:
        from quoting.api.approval_store import ApprovalStore

        return ApprovalStore(repo or self.review_repo())

    def progress_store(
        self,
        repo: SQLiteReviewRepository | None = None,
    ) -> ProgressStore:
        from quoting.api.progress_store import ProgressStore

        return ProgressStore(repo or self.review_repo())

    def review_data_service(
        self,
        repo: SQLiteReviewRepository | None = None,
        approval_store: ApprovalStore | None = None,
    ) -> ReviewDataService:
        from quoting.api.services.review_service import ReviewDataService

        active_repo = repo or self.review_repo()
        approvals = approval_store or self.approval_store(active_repo)
        return ReviewDataService(active_repo, approval_store=approvals)

    def review_read_service(
        self,
        repo: SQLiteReviewRepository | None = None,
    ) -> ReviewReadService:
        from quoting.api.services.review_read_service import ReviewReadService

        return ReviewReadService(repo or self.review_repo())

    def job_queue(
        self,
        repo: SQLiteReviewRepository | None = None,
    ) -> JobQueue:
        if self._job_queue is None:
            from quoting.api.job_queue import JobQueue

            self._job_queue = JobQueue(repo or self.review_repo())
        return self._job_queue

    def step_handlers(self) -> StepHandlers:
        if self._step_handlers is None:
            from quoting.api.step_handlers import StepHandlers

            repo = self.review_repo()
            self._step_handlers = StepHandlers(
                repo=repo,
                pipeline=self.pipeline(),
                progress_store=self.progress_store(repo),
            )
        return self._step_handlers

    def pipeline_coordinator(
        self,
        *,
        review_ui_base_url: str = "http://localhost:8501",
    ) -> PipelineCoordinator:
        """Build (and cache) the coordinator that drives review pipelines.

        The coordinator is a singleton owned by the FastAPI lifespan; the
        worker dispatches against ``coordinator.worker_handlers()`` and
        ``ReviewWorkflowService`` enqueues new runs via
        ``coordinator.start_pipeline``.
        """
        if self._pipeline_coordinator is None:
            from quoting.api.pipeline_coordinator import PipelineCoordinator

            repo = self.review_repo()

            def build_completion_payload(review_id: str) -> dict:
                from quoting.reviews import api_base_url

                base = api_base_url()
                return {
                    "review_id": review_id,
                    "review_url": f"{review_ui_base_url}?review_id={review_id}",
                    "draft_pdf_url": f"{base}/api/reviews/{review_id}/pdf/draft",
                    "final_pdf_url": f"{base}/api/reviews/{review_id}/pdf/final",
                    "status_url": f"{base}/api/reviews/{review_id}/status",
                    "approval_url": f"{base}/api/reviews/{review_id}/approval",
                    "status": "completed",
                }

            self._pipeline_coordinator = PipelineCoordinator(
                handlers=self.step_handlers(),
                queue=self.job_queue(repo),
                progress=self.progress_store(repo),
                completion_payload_builder=build_completion_payload,
            )
        return self._pipeline_coordinator

    def review_workflow_service(
        self,
        *,
        pipeline: QuotingPipeline | None = None,
        review_ui_base_url: str = "http://localhost:8501",
        settings_loader: SettingsLoader | None = None,
        review_data_loader: ReviewDataLoader | None = None,
        quotation_builder: QuotationBuilder | None = None,
        quality_gate_evaluator: QualityGateEvaluator | None = None,
        pdf_builder: PdfBuilder | None = None,
        approval_transition: ApprovalTransition | None = None,
    ) -> ReviewWorkflowService:
        from quoting.api.services.quality_gate_service import evaluate_quality_gate
        from quoting.api.services.quotation_service import build_quotation_with_overrides
        from quoting.api.services.review_workflow_service import ReviewWorkflowService
        from quoting.api.settings_store import load_user_settings
        from quoting.output import build_draft_pdf

        repo = self.review_repo()
        approvals = self.approval_store(repo)
        review_data = self.review_data_service(repo, approval_store=approvals)
        review_reads = self.review_read_service(repo)

        return ReviewWorkflowService(
            repo=repo,
            pipeline=pipeline or self.pipeline(),
            review_ui_base_url=review_ui_base_url,
            settings_loader=settings_loader or load_user_settings,
            review_data_loader=review_data_loader,
            quotation_builder=quotation_builder or build_quotation_with_overrides,
            quality_gate_evaluator=quality_gate_evaluator or evaluate_quality_gate,
            pdf_builder=pdf_builder or build_draft_pdf,
            approval_store=approvals,
            progress_store=self.progress_store(repo),
            review_data=review_data,
            review_read_service=review_reads,
            approval_transition=approval_transition,
            coordinator=self.pipeline_coordinator(review_ui_base_url=review_ui_base_url),
        )


_DEFAULT_CONTAINER: AppContainer | None = None


def get_app_container() -> AppContainer:
    global _DEFAULT_CONTAINER
    if _DEFAULT_CONTAINER is None:
        _DEFAULT_CONTAINER = AppContainer()
    return _DEFAULT_CONTAINER


def reset_app_container() -> None:
    """Test helper for code that needs to rebuild lazily-owned dependencies."""
    global _DEFAULT_CONTAINER
    _DEFAULT_CONTAINER = None
