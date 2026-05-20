"""Application service for review workflows.

The routers should stay thin HTTP adapters. This module owns the orchestration
for review-detail loading and user-driven mutations such as editing positions,
regenerating the draft PDF, and finalizing a quotation.
"""
from __future__ import annotations

import base64
import logging
import shutil
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException
from pydantic import ValidationError

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
    resolve_filename_template,
    sanitize_pdf_filename,
)
from quoting.api.services.review_read_service import ReviewReadService
from quoting.api.services.review_service import (
    ReviewDataService,
    enrich_exact_article_edits,
)
from quoting.api.settings_store import AppSettings, load_user_settings
from quoting.core import Anfrage
from quoting.ingestion import Mail
from quoting.matching import MatchResult, match_positions
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline, StepProgress
from quoting.pricing import Quotation
from quoting.reviews import (
    api_base_url,
    draft_pdf_filename,
    final_pdf_filename,
    reset_review_artifacts,
)
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

log = logging.getLogger("quoting.frontend_router")

ReviewDataLoader = Callable[
    [str, QuotingPipeline],
    tuple[Anfrage, list[MatchResult], list[dict]],
]
QuotationBuilder = Callable[[Anfrage, list, list, Path, str], Quotation]
QualityGateEvaluator = Callable[
    [Anfrage, list[MatchResult], Quotation | None, list[dict] | None],
    QualityGateResult,
]
PdfBuilder = Callable[..., None]
SettingsLoader = Callable[[], AppSettings]
PipelineScheduler = Callable[[str, Path, Mail], None]
ApprovalTransition = Callable[..., ApprovalRecord]


@dataclass(frozen=True)
class IncomingMailAttachment:
    name: str
    content_type: str | None = None
    size: int | None = None
    id: str | None = None
    content_base64: str | None = None

    def meta_dict(self) -> dict:
        result: dict[str, Any] = {"name": self.name}
        if self.content_type is not None:
            result["contentType"] = self.content_type
        if self.size is not None:
            result["size"] = self.size
        if self.id is not None:
            result["id"] = self.id
        return result


@dataclass(frozen=True)
class IncomingMailReview:
    subject: str
    sender: str
    body: str
    attachments: list[IncomingMailAttachment]
    outlook_item_id: str | None = None


def format_mail_dict(mail_meta: dict) -> dict:
    return {
        "subject": str(mail_meta.get("subject") or ""),
        "from": str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        "body": str(mail_meta.get("body") or ""),
        "attachments": list(mail_meta.get("attachments") or []),
    }


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

    def create_review_from_mail(
        self,
        payload: IncomingMailReview,
        *,
        schedule_pipeline: PipelineScheduler,
    ) -> dict:
        review_id = uuid.uuid4().hex[:12]
        self.repo.create_review(
            review_id,
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            source="outlook",
            outlook_item_id=payload.outlook_item_id,
        )
        folder = self.repo.artifact_dir(review_id)
        folder.mkdir(parents=True, exist_ok=True)

        self.progress_store_for_review.init(review_id)
        self.approvals.reset(review_id)

        try:
            mail = self._prepare_mail_payload(payload, review_id, folder)
            self.progress_store_for_review.update_step(
                review_id,
                "Mail vorbereiten",
                "completed",
                "Mail und Anhänge gespeichert",
            )
        except Exception as exc:
            self.progress_store_for_review.fail(review_id, str(exc))
            raise HTTPException(400, f"Could not prepare mail: {exc}") from exc

        schedule_pipeline(review_id, folder, mail)
        return self.build_review_response(review_id, status="running")

    def reset_review(
        self,
        review_id: str,
        *,
        schedule_pipeline: PipelineScheduler,
    ) -> dict:
        """Reset a review and re-run the pipeline against the saved mail."""
        reset_review_artifacts(
            review_id,
            repo=self.repo,
            progress_store=self.progress_store_for_review,
            approval_store=self.approvals,
        )

        mail = self._rehydrate_mail(review_id)
        schedule_pipeline(review_id, self.repo.artifact_dir(review_id), mail)

        base = api_base_url()
        return {
            "review_id": review_id,
            "status": "running",
            "status_url": f"{base}/api/reviews/{review_id}/status",
        }

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

    def run_review_pipeline(
        self,
        review_id: str,
        folder: Path,
        mail: Mail,
    ) -> None:
        def on_progress(progress: StepProgress) -> None:
            self.progress_store_for_review.update_step(
                review_id=review_id,
                step_name=progress.step_name,
                status=progress.status,
                detail=progress.detail,
            )

        try:
            # Initial pipeline run is always a draft (with red warning).
            # Final/approved PDFs get re-rendered later by the UI.
            result = self.pipeline.run(
                mail,
                output_dir=folder,
                work_name="pipeline",
                progress=on_progress,
                is_final=False,
                snapshot_sink=lambda name, data: self.repo.save_payload(review_id, name, data),
            )
            self.repo.register_document(
                review_id,
                kind="draft_pdf",
                path=result.pdf_path,
                filename=result.pdf_path.name,
                content_type="application/pdf",
            )
            response = self.build_review_response(review_id, status="completed")
            response["summary"] = result.summary()
            self.progress_store_for_review.complete(review_id, response)
        except Exception as exc:
            log.error(
                "Pipeline failed for review %s: %s\n%s",
                review_id,
                exc,
                traceback.format_exc(),
            )
            self.progress_store_for_review.fail(review_id, str(exc))

    def build_review_response(self, review_id: str, *, status: str) -> dict:
        base = api_base_url()
        return {
            "review_id": review_id,
            "review_url": f"{self.review_ui_base_url}?review_id={review_id}",
            "draft_pdf_url": f"{base}/api/reviews/{review_id}/pdf/draft",
            "draft_pdf_filename": draft_pdf_filename(review_id),
            "final_pdf_url": f"{base}/api/reviews/{review_id}/pdf/final",
            "final_pdf_filename": final_pdf_filename(review_id),
            "status_url": f"{base}/api/reviews/{review_id}/status",
            "approval_url": f"{base}/api/reviews/{review_id}/approval",
            "status": status,
        }

    def list_reviews(self, summaries: list[Any] | None = None) -> list[dict]:
        summaries = summaries if summaries is not None else self.review_reads.scan_reviews()
        return [
            {
                "review_id": s.review_id,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "subject": s.subject,
                "sender": s.sender,
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
                "extracted_articles": s.extracted_articles,
            }
            for s in summaries
        ]

    def get_detail(self, review_id: str) -> dict:
        anfrage = self.review_data_service.load_or_extract_anfrage(review_id, self.pipeline)
        original_anfrage = (
            self.review_data_service.try_load_original_anfrage(review_id) or anfrage
        )
        matches = self.review_data_service.load_or_recompute_matches(
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

    def delete_review(self, review_id: str) -> None:
        folder = self.repo.artifact_dir(review_id)
        try:
            if folder.exists():
                shutil.rmtree(folder)
            self.repo.delete_review(review_id)
        except OSError as exc:
            log.exception("delete_review: could not delete %s", review_id)
            raise HTTPException(500, f"Review konnte nicht gelöscht werden: {exc}") from exc

    def get_mail(self, review_id: str) -> dict:
        meta = self.repo.load_mail(review_id) or {}
        return format_mail_dict(meta)

    def update_anfrage(self, review_id: str, payload: dict) -> dict:
        try:
            anfrage = Anfrage.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(400, f"Invalid Anfrage payload: {exc}") from exc

        previous = self.review_data_service.try_load_anfrage(review_id)
        anfrage = enrich_exact_article_edits(anfrage, previous, self.pipeline)

        self.repo.save_anfrage_reviewed(review_id, anfrage.model_dump(mode="json"))
        if self.repo.has_matches_reviewed(review_id):
            matches = self.review_data_service.load_or_recompute_matches(
                review_id,
                anfrage,
                self.pipeline,
            )
            self.repo.save_matches_reviewed(review_id, [m.to_dict() for m in matches])
        else:
            try:
                matches = match_positions(
                    anfrage.positionen,
                    self.pipeline.stammdaten,
                    fuzzy_threshold=self.pipeline.settings.fuzzy_threshold,
                    semantic_threshold=self.pipeline.settings.semantic_threshold,
                )
            except Exception as exc:
                log.exception("put_anfrage: match recompute failed for %s", review_id)
                raise HTTPException(422, f"Matching fehlgeschlagen: {exc}") from exc
            self.repo.save_matches_initial(review_id, [m.to_dict() for m in matches])

        self.review_data_service.invalidate_approval(review_id)
        return anfrage.model_dump(mode="json")

    def save_overrides(self, review_id: str, payload: list[dict]) -> list[dict]:
        if not isinstance(payload, list):
            raise HTTPException(400, "Overrides payload must be a list")

        self.repo.save_overrides(review_id, payload)
        self.review_data_service.invalidate_approval(review_id)
        return payload

    def regenerate_quotation(self, review_id: str) -> dict:
        folder = self._review_dir(review_id)
        anfrage, matches, overrides = self._load_review_data(review_id)
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
            raise HTTPException(422, f"PDF-Erstellung fehlgeschlagen: {exc}") from exc

        self.repo.register_document(
            review_id,
            kind="draft_pdf",
            path=pdf_path,
            filename=pdf_path.name,
            content_type="application/pdf",
        )
        self.repo.save_quotation_reviewed(review_id, quotation.to_dict())
        return quotation.to_dict()

    def finalize_quotation(
        self,
        review_id: str,
        *,
        actor: str,
        filename: str | None,
        warning_acknowledged: bool,
        exception_reason: str | None,
    ) -> dict:
        folder = self._review_dir(review_id)
        anfrage, matches, overrides = self._load_review_data(review_id)
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
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Freigabe benötigt eine bewusste Bestätigung offener Prüfpunkte.",
                    "quality_gate": quality_gate.to_dict(),
                },
            )

        if filename:
            final_filename = sanitize_pdf_filename(filename)
        else:
            template = user_settings.workflow.final_pdf_filename_template or "Angebot_[Kunde].pdf"
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
            raise HTTPException(422, f"Final-PDF konnte nicht erstellt werden: {exc}") from exc

        try:
            transition = self.approval_transition or self.approvals.transition
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
            # Roll back the just-written final PDF so the filesystem doesn't
            # diverge from the approval state.
            final_path.unlink(missing_ok=True)
            log.exception("finalize: approval transition failed for %s; rolled back PDF", review_id)
            raise HTTPException(500, f"Status-Übergang fehlgeschlagen: {exc}") from exc

        self.repo.register_document(
            review_id,
            kind="final_pdf",
            path=final_path,
            filename=final_path.name,
            content_type="application/pdf",
        )
        return {"final_pdf_path": record.final_pdf_path or final_path.name}

    def _load_review_data(self, review_id: str) -> tuple[Anfrage, list[MatchResult], list[dict]]:
        loader = self.review_data_loader
        if loader is not None:
            return loader(review_id, self.pipeline)
        return load_review_data(
            review_id,
            self.pipeline,
            repo=self.repo,
            review_data_service=self.review_data_service,
        )

    def _review_dir(self, review_id: str) -> Path:
        folder = self.repo.artifact_dir(review_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _decode_and_save_attachments(
        self,
        attachments: list[IncomingMailAttachment],
        review_id: str,
        folder: Path,
    ) -> list[Path]:
        """Decode base64 attachments and write them to folder. Returns saved paths."""
        saved: list[Path] = []
        for attachment in attachments:
            if not attachment.content_base64:
                continue
            safe_name = Path(attachment.name).name or f"attachment_{len(saved)}"
            target = folder / safe_name
            try:
                target.write_bytes(base64.b64decode(attachment.content_base64))
            except Exception as exc:
                raise HTTPException(
                    400,
                    f"Bad base64 in attachment '{attachment.name}': {exc}",
                ) from exc
            self.repo.register_document(
                review_id,
                kind="attachment",
                path=target,
                filename=safe_name,
                content_type=attachment.content_type,
            )
            saved.append(target)
        return saved

    def _prepare_mail_payload(
        self,
        payload: IncomingMailReview,
        review_id: str,
        folder: Path,
    ) -> Mail:
        meta = {
            "subject": payload.subject,
            "from": payload.sender,
            "body": payload.body,
            "attachments": [attachment.meta_dict() for attachment in payload.attachments],
        }
        self.repo.save_mail(review_id, meta)

        saved_paths = self._decode_and_save_attachments(payload.attachments, review_id, folder)

        mail = Mail(
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            attachments=saved_paths,
        )
        if not mail.has_content:
            raise HTTPException(
                status_code=400,
                detail="Mail has neither body text nor attachments — nothing to extract.",
            )
        return mail

    def _rehydrate_mail(self, review_id: str) -> Mail:
        """Rebuild a Mail from the persisted review input payload for resets."""
        meta = self.repo.load_mail(review_id)
        if meta is None:
            raise HTTPException(400, "No persisted mail payload — review cannot be reset")

        mail = self.review_data_service.mail_from_meta(meta, review_id)
        if not mail.has_content:
            raise HTTPException(400, "Reset failed: mail has no body and no registered attachments.")
        return mail
