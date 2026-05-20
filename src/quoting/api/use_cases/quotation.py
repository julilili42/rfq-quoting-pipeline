from __future__ import annotations

import logging
from dataclasses import dataclass

from quoting.api.approval_store import ApprovalStore
from quoting.api.services.quotation_service import (
    resolve_filename_template,
    sanitize_pdf_filename,
)
from quoting.api.services.review_service import ReviewDataService
from quoting.api.use_cases.common import (
    ApprovalTransition,
    PdfBuilder,
    QualityGateEvaluator,
    QuotationBuilder,
    ReviewDataLoader,
    SettingsLoader,
    load_review_data_for_use_case,
    review_dir,
)
from quoting.api.use_cases.errors import (
    UseCaseConflict,
    UseCaseFailure,
    UseCaseUnprocessable,
)
from quoting.pipeline import QuotingPipeline
from quoting.reviews import draft_pdf_filename
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

log = logging.getLogger("quoting.frontend_router")


@dataclass
class RegenerateQuotationUseCase:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    settings_loader: SettingsLoader
    review_data_loader: ReviewDataLoader | None
    review_data: ReviewDataService
    quotation_builder: QuotationBuilder
    pdf_builder: PdfBuilder

    def execute(self, review_id: str) -> dict:
        folder = review_dir(self.repo, review_id)
        anfrage, matches, overrides = load_review_data_for_use_case(
            review_id,
            pipeline=self.pipeline,
            repo=self.repo,
            review_data=self.review_data,
            review_data_loader=self.review_data_loader,
        )
        company_profile = self.settings_loader().company
        quotation = self.quotation_builder(
            anfrage,
            matches,
            overrides,
            self.pipeline.settings.preise_path,
            review_id,
        )

        pdf_path = folder / draft_pdf_filename(review_id)
        try:
            self.pdf_builder(
                anfrage,
                quotation,
                pdf_path,
                is_final=False,
                company_profile=company_profile,
            )
        except Exception as exc:
            log.exception("regenerate: PDF build failed for %s", review_id)
            raise UseCaseUnprocessable(
                f"PDF-Erstellung fehlgeschlagen: {exc}"
            ) from exc

        self.repo.register_document(
            review_id,
            kind="draft_pdf",
            path=pdf_path,
            filename=pdf_path.name,
            content_type="application/pdf",
        )
        self.repo.save_quotation_reviewed(review_id, quotation.to_dict())
        return quotation.to_dict()


@dataclass
class FinalizeQuotationUseCase:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    settings_loader: SettingsLoader
    review_data_loader: ReviewDataLoader | None
    review_data: ReviewDataService
    quotation_builder: QuotationBuilder
    quality_gate_evaluator: QualityGateEvaluator
    pdf_builder: PdfBuilder
    approval_store: ApprovalStore
    approval_transition: ApprovalTransition | None = None

    def execute(
        self,
        review_id: str,
        *,
        actor: str,
        filename: str | None,
        warning_acknowledged: bool,
        exception_reason: str | None,
    ) -> dict:
        folder = review_dir(self.repo, review_id)
        anfrage, matches, overrides = load_review_data_for_use_case(
            review_id,
            pipeline=self.pipeline,
            repo=self.repo,
            review_data=self.review_data,
            review_data_loader=self.review_data_loader,
        )
        user_settings = self.settings_loader()
        company_profile = user_settings.company
        quotation = self.quotation_builder(
            anfrage,
            matches,
            overrides,
            self.pipeline.settings.preise_path,
            review_id,
        )
        quality_gate = self.quality_gate_evaluator(anfrage, matches, quotation, overrides)
        if quality_gate.requires_acknowledgement and not warning_acknowledged:
            raise UseCaseConflict(
                {
                    "message": "Freigabe benötigt eine bewusste Bestätigung offener Prüfpunkte.",
                    "quality_gate": quality_gate.to_dict(),
                },
            )

        if filename:
            final_filename = sanitize_pdf_filename(filename)
        else:
            template = (
                user_settings.workflow.final_pdf_filename_template
                or "Angebot_[Kunde].pdf"
            )
            final_filename = resolve_filename_template(template, anfrage, review_id)

        final_path = folder / final_filename
        try:
            self.pdf_builder(
                anfrage,
                quotation,
                final_path,
                is_final=True,
                company_profile=company_profile,
            )
        except Exception as exc:
            log.exception("finalize: PDF build failed for %s", review_id)
            raise UseCaseUnprocessable(
                f"Final-PDF konnte nicht erstellt werden: {exc}"
            ) from exc

        try:
            transition = self.approval_transition or self.approval_store.transition
            record = transition(
                review_id,
                target="approved",
                actor=actor,
                warning_acknowledged=bool(
                    warning_acknowledged and quality_gate.requires_acknowledgement
                ),
                exception_reason=exception_reason,
                final_pdf_path=final_path.name,
            )
        except Exception as exc:
            final_path.unlink(missing_ok=True)
            log.exception(
                "finalize: approval transition failed for %s; rolled back PDF",
                review_id,
            )
            raise UseCaseFailure(f"Status-Übergang fehlgeschlagen: {exc}") from exc

        self.repo.register_document(
            review_id,
            kind="final_pdf",
            path=final_path,
            filename=final_path.name,
            content_type="application/pdf",
        )
        return {"final_pdf_path": record.final_pdf_path or final_path.name}
