"""Review list, detail, mail, and mutation endpoints (PUT anfrage/overrides, regenerate, finalize)."""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError

from quoting.api import _common
from quoting.api.progress_store import read_progress
from quoting.api.services import review_service as rs
from quoting.api.services.quality_gate_service import evaluate_quality_gate
from quoting.api.services.quotation_service import (
    build_quotation_with_overrides,
    filter_redundant_custom_price_overrides,
    resolve_filename_template,
    sanitize_pdf_filename,
)
from quoting.api.settings_store import load_user_settings
from quoting.core import Anfrage
from quoting.matching import match_positions
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline
from quoting.reviews import (
    draft_pdf_filename,
    find_draft_pdf,
    find_final_pdf,
    get_default_repository,
    load_saved_quotation,
    scan_reviews,
)

log = logging.getLogger("quoting.frontend_router")

router = APIRouter()


def _format_mail_dict(mail_meta: dict) -> dict:
    return {
        "subject": str(mail_meta.get("subject") or ""),
        "from": str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        "body": str(mail_meta.get("body") or ""),
        "attachments": list(mail_meta.get("attachments") or []),
    }


def _load_review_data(review_id: str, pipeline: QuotingPipeline) -> tuple:
    """Load anfrage, matches, and overrides for a review."""
    try:
        anfrage = rs.load_or_extract_anfrage(review_id, pipeline)
    except Exception as exc:
        log.exception("load_review_data: anfrage load failed for %s", review_id)
        raise HTTPException(422, f"Anfrage konnte nicht geladen werden: {exc}") from exc

    try:
        matches = rs.load_or_recompute_matches(review_id, anfrage, pipeline)
    except Exception as exc:
        log.exception("load_review_data: match recompute failed for %s", review_id)
        raise HTTPException(422, f"Matching fehlgeschlagen: {exc}") from exc

    overrides = get_default_repository().load_overrides(review_id)
    overrides = filter_redundant_custom_price_overrides(overrides, matches)
    return anfrage, matches, overrides


@router.get("/reviews")
def list_reviews() -> list[dict]:
    summaries = scan_reviews()
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


@router.get("/reviews/{review_id}")
def get_review_detail(review_id: str) -> dict:
    _common.require_review(review_id)
    pipeline = _common.get_pipeline()
    repo = get_default_repository()

    anfrage = rs.load_or_extract_anfrage(review_id, pipeline)
    original_anfrage = rs.try_load_original_anfrage(review_id) or anfrage
    matches = rs.load_or_recompute_matches(review_id, anfrage, pipeline)
    quotation = load_saved_quotation(review_id)

    overrides = repo.load_overrides(review_id)
    overrides = filter_redundant_custom_price_overrides(overrides, matches)

    mail_meta = repo.load_mail(review_id) or {}
    progress = read_progress(review_id) or {}

    return {
        "review_id": review_id,
        "created_at": progress.get("created_at"),
        "anfrage": anfrage.model_dump(mode="json"),
        "original_anfrage": original_anfrage.model_dump(mode="json"),
        "matches": [m.to_dict() for m in matches],
        "quotation": quotation.to_dict() if quotation else None,
        "manual_overrides": overrides,
        "mail": _format_mail_dict(mail_meta),
        "has_draft_pdf": find_draft_pdf(review_id) is not None,
        "has_final_pdf": find_final_pdf(review_id) is not None,
    }


@router.delete("/reviews/{review_id}", status_code=204)
def delete_review(review_id: str) -> Response:
    _common.require_review(review_id)
    repo = get_default_repository()
    folder = repo.artifact_dir(review_id)
    try:
        if folder.exists():
            shutil.rmtree(folder)
        repo.delete_review(review_id)
    except OSError as exc:
        log.exception("delete_review: could not delete %s", review_id)
        raise HTTPException(500, f"Review konnte nicht gelöscht werden: {exc}") from exc
    return Response(status_code=204)


@router.get("/reviews/{review_id}/mail")
def get_review_mail(review_id: str) -> dict:
    _common.require_review(review_id)
    meta = get_default_repository().load_mail(review_id) or {}
    return _format_mail_dict(meta)


# --------------------------------------------------------------------------- mutations
class AnfragePayload(BaseModel):
    model_config = {"extra": "allow"}


@router.put("/reviews/{review_id}/anfrage")
def put_anfrage(review_id: str, payload: dict) -> dict:
    _common.require_review(review_id)
    repo = get_default_repository()

    try:
        anfrage = Anfrage.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid Anfrage payload: {exc}") from exc

    pipeline = _common.get_pipeline()
    previous = rs.try_load_anfrage(review_id)
    anfrage = rs.enrich_exact_article_edits(anfrage, previous, pipeline)

    repo.save_anfrage_reviewed(review_id, anfrage.model_dump(mode="json"))
    if repo.has_matches_reviewed(review_id):
        matches = rs.load_or_recompute_matches(review_id, anfrage, pipeline)
        repo.save_matches_reviewed(review_id, [m.to_dict() for m in matches])
    else:
        try:
            matches = match_positions(
                anfrage.positionen,
                pipeline.stammdaten,
                fuzzy_threshold=pipeline.settings.fuzzy_threshold,
                semantic_threshold=pipeline.settings.semantic_threshold,
            )
        except Exception as exc:
            log.exception("put_anfrage: match recompute failed for %s", review_id)
            raise HTTPException(422, f"Matching fehlgeschlagen: {exc}") from exc
        repo.save_matches_initial(review_id, [m.to_dict() for m in matches])

    rs.invalidate_approval(review_id)

    return anfrage.model_dump(mode="json")


@router.put("/reviews/{review_id}/overrides")
def put_overrides(review_id: str, payload: list[dict]) -> list[dict]:
    _common.require_review(review_id)

    if not isinstance(payload, list):
        raise HTTPException(400, "Overrides payload must be a list")

    get_default_repository().save_overrides(review_id, payload)
    rs.invalidate_approval(review_id)

    return payload


@router.post("/reviews/{review_id}/regenerate")
def regenerate_quotation(review_id: str) -> dict:
    folder = _common.review_dir(review_id)
    pipeline = _common.get_pipeline()
    repo = get_default_repository()

    anfrage, matches, overrides = _load_review_data(review_id, pipeline)
    company_profile = load_user_settings().company
    quotation = build_quotation_with_overrides(
        anfrage, matches, overrides, pipeline.settings.preise_path, review_id
    )

    pdf_path = folder / draft_pdf_filename(review_id)
    try:
        build_draft_pdf(anfrage, quotation, pdf_path, is_final=False, company_profile=company_profile)
    except Exception as exc:
        log.exception("regenerate: PDF build failed for %s", review_id)
        raise HTTPException(422, f"PDF-Erstellung fehlgeschlagen: {exc}") from exc

    repo.register_document(
        review_id,
        kind="draft_pdf",
        path=pdf_path,
        filename=pdf_path.name,
        content_type="application/pdf",
    )
    repo.save_quotation_reviewed(review_id, quotation.to_dict())
    return quotation.to_dict()


class FinalizeRequest(BaseModel):
    actor: str = Field(min_length=1)
    filename: str | None = None
    warning_acknowledged: bool = False
    exception_reason: str | None = Field(default=None, max_length=1000)


@router.post("/reviews/{review_id}/finalize")
def finalize_quotation(review_id: str, payload: FinalizeRequest) -> dict:
    folder = _common.review_dir(review_id)
    pipeline = _common.get_pipeline()
    repo = get_default_repository()

    anfrage, matches, overrides = _load_review_data(review_id, pipeline)
    user_settings = load_user_settings()
    company_profile = user_settings.company
    quotation = build_quotation_with_overrides(
        anfrage, matches, overrides, pipeline.settings.preise_path, review_id
    )
    quality_gate = evaluate_quality_gate(anfrage, matches, quotation, overrides)
    if quality_gate.requires_acknowledgement and not payload.warning_acknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Freigabe benötigt eine bewusste Bestätigung offener Prüfpunkte.",
                "quality_gate": quality_gate.to_dict(),
            },
        )

    if payload.filename:
        final_filename = sanitize_pdf_filename(payload.filename)
    else:
        template = user_settings.workflow.final_pdf_filename_template or "Angebot_[Kunde].pdf"
        final_filename = resolve_filename_template(template, anfrage, review_id)

    final_path = folder / final_filename
    try:
        build_draft_pdf(anfrage, quotation, final_path, is_final=True, company_profile=company_profile)
    except Exception as exc:
        log.exception("finalize: PDF build failed for %s", review_id)
        raise HTTPException(422, f"Final-PDF konnte nicht erstellt werden: {exc}") from exc

    from quoting.api.approval_store import transition

    try:
        record = transition(
            review_id,
            target="approved",
            actor=payload.actor,
            warning_acknowledged=bool(
                payload.warning_acknowledged and quality_gate.requires_acknowledgement
            ),
            exception_reason=payload.exception_reason,
            final_pdf_path=final_path.name,
        )
    except Exception as exc:
        # Roll back the just-written final PDF so the filesystem doesn't
        # diverge from the approval state.
        final_path.unlink(missing_ok=True)
        log.exception("finalize: approval transition failed for %s; rolled back PDF", review_id)
        raise HTTPException(500, f"Status-Übergang fehlgeschlagen: {exc}") from exc

    repo.register_document(
        review_id,
        kind="final_pdf",
        path=final_path,
        filename=final_path.name,
        content_type="application/pdf",
    )
    return {"final_pdf_path": record.final_pdf_path or final_path.name}
