"""Review list, detail, mail, and mutation endpoints (PUT anfrage/overrides, regenerate, finalize)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from quoting.api import _common
from quoting.api.response_models import (
    FinalizeResponse,
    MailMeta,
    ManualOverridePayload,
    QuotationModel,
    ReplyBodyResponse,
    ReviewDetail,
    ReviewListItem,
)
from quoting.api.services.quality_gate_service import evaluate_quality_gate
from quoting.api.services.quotation_service import build_quotation_with_overrides
from quoting.api.services.review_workflow_service import (
    ReviewWorkflowService,
    format_mail_dict,
)
from quoting.api.services.review_workflow_service import (
    load_review_data as _service_load_review_data,
)
from quoting.api.settings_store import load_user_settings
from quoting.core import Anfrage
from quoting.extraction.llm import build_llm
from quoting.output import build_draft_pdf
from quoting.output.reply_body_prompt import generate_reply_body
from quoting.pipeline import QuotingPipeline
from quoting.pricing import Quotation, QuotationItem

router = APIRouter()


def _format_mail_dict(mail_meta: dict) -> dict:
    return format_mail_dict(mail_meta)


def _workflow_service(
    *,
    pipeline: QuotingPipeline | None = None,
) -> ReviewWorkflowService:
    return _common.get_review_workflow_service(
        pipeline=pipeline or _common.get_pipeline(),
        settings_loader=load_user_settings,
        review_data_loader=_load_review_data,
        quotation_builder=build_quotation_with_overrides,
        quality_gate_evaluator=evaluate_quality_gate,
        pdf_builder=build_draft_pdf,
    )


def _load_review_data(
    review_id: str,
    pipeline: QuotingPipeline,
) -> tuple:
    return _service_load_review_data(
        review_id,
        pipeline,
        repo=_common.get_review_repo(),
    )


@router.get("/reviews", response_model=list[ReviewListItem])
def list_reviews() -> list[dict]:
    return _workflow_service().list_reviews()


def _review_by_outlook_item_status(outlook_item_id: str) -> dict:
    """Compact status payload for the review bound to ``outlook_item_id``.

    Used by the Outlook add-in to render the right workflow card without
    keeping any state in localStorage. 404 when no review is bound.
    """
    status = _workflow_service().get_outlook_item_status(outlook_item_id)
    if status is None:
        raise HTTPException(404, f"No review bound to Outlook item {outlook_item_id}")
    return status


@router.get("/reviews/by-outlook-item")
def get_review_by_outlook_item_query(outlook_item_id: str) -> dict:
    """Query-param variant for Outlook IDs containing slashes."""
    return _review_by_outlook_item_status(outlook_item_id)


@router.get("/reviews/by-outlook-item/{outlook_item_id}")
def get_review_by_outlook_item(outlook_item_id: str) -> dict:
    return _review_by_outlook_item_status(outlook_item_id)


def _detach_outlook_item(outlook_item_id: str) -> Response:
    """Unlink the review currently bound to ``outlook_item_id``.

    The review is preserved (still reachable via the overview); the
    Outlook plugin reverts to "new" for this mail.
    """
    _workflow_service().detach_outlook_item(outlook_item_id)
    return Response(status_code=204)


@router.post("/reviews/by-outlook-item/detach", status_code=204)
def detach_outlook_item_query(outlook_item_id: str) -> Response:
    """Query-param variant for Outlook IDs containing slashes."""
    return _detach_outlook_item(outlook_item_id)


@router.post("/reviews/by-outlook-item/{outlook_item_id}/detach", status_code=204)
def detach_outlook_item(outlook_item_id: str) -> Response:
    return _detach_outlook_item(outlook_item_id)


@router.post("/reviews/{review_id}/mark-opened")
def mark_review_opened(review_id: str) -> dict:
    """Record the first time the Review-UI was opened for ``review_id``."""
    _common.require_review(review_id)
    return _workflow_service().mark_review_opened(review_id)


@router.get("/reviews/{review_id}", response_model=ReviewDetail)
def get_review_detail(review_id: str) -> dict:
    _common.require_review(review_id)
    return _common.run_use_case(lambda: _workflow_service().get_detail(review_id))


@router.delete("/reviews/{review_id}", status_code=204)
def delete_review(review_id: str) -> Response:
    _common.require_review(review_id)
    _common.run_use_case(lambda: _workflow_service().delete_review(review_id))
    return Response(status_code=204)


@router.get("/reviews/{review_id}/mail", response_model=MailMeta)
def get_review_mail(review_id: str) -> dict:
    _common.require_review(review_id)
    return _workflow_service().get_mail(review_id)


# --------------------------------------------------------------------------- mutations
class AnfragePayload(BaseModel):
    model_config = {"extra": "allow"}


@router.put("/reviews/{review_id}/anfrage", response_model=Anfrage)
def put_anfrage(review_id: str, payload: dict) -> dict:
    _common.require_review(review_id)
    return _common.run_use_case(
        lambda: _workflow_service().update_anfrage(review_id, payload)
    )


@router.put("/reviews/{review_id}/overrides", response_model=list[ManualOverridePayload])
def put_overrides(review_id: str, payload: list[dict]) -> list[dict]:
    _common.require_review(review_id)
    return _common.run_use_case(
        lambda: _workflow_service().save_overrides(review_id, payload)
    )


class RequirementsAckRequest(BaseModel):
    indices: list[int] = Field(default_factory=list)


@router.put("/reviews/{review_id}/requirements-ack")
def put_requirements_ack(review_id: str, payload: RequirementsAckRequest) -> dict:
    """Persist which extracted requirements have been acknowledged by the user."""
    _common.require_review(review_id)
    repo = _common.get_review_repo()

    anfrage_dict = repo.load_anfrage(review_id) or {}
    total = len(anfrage_dict.get("anforderungen", []) or [])
    for idx in payload.indices:
        if idx < 0 or idx >= total:
            raise HTTPException(
                422,
                f"Index {idx} is out of range (0..{total - 1 if total else -1})",
            )

    repo.save_requirements_acknowledged(review_id, payload.indices)
    return {"indices": repo.load_requirements_acknowledged(review_id)}


@router.post("/reviews/{review_id}/regenerate", response_model=QuotationModel)
def regenerate_quotation(review_id: str) -> dict:
    _common.require_review(review_id)
    return _common.run_use_case(
        lambda: _workflow_service().regenerate_quotation(review_id)
    )


class FinalizeRequest(BaseModel):
    actor: str = Field(min_length=1)
    filename: str | None = None
    warning_acknowledged: bool = False
    exception_reason: str | None = Field(default=None, max_length=1000)


def _quotation_from_dict(data: dict) -> Quotation:
    items = [QuotationItem(**item) for item in data.get("items", [])]
    payload = {k: v for k, v in data.items() if k != "items"}
    return Quotation(items=items, **payload)


@router.get("/reviews/{review_id}/reply-body", response_model=ReplyBodyResponse)
def get_reply_body(review_id: str) -> ReplyBodyResponse:
    """Generate a short, contextual cover-letter body for the Outlook reply."""
    _common.require_review(review_id)
    repo = _common.get_review_repo()

    anfrage_dict = repo.load_anfrage(review_id)
    quotation_dict = repo.load_quotation(review_id)
    mail = repo.load_mail(review_id) or {}
    if not anfrage_dict or not quotation_dict:
        raise HTTPException(409, "Anfrage or quotation not yet available for this review")

    try:
        anfrage = Anfrage.model_validate(anfrage_dict)
        quotation = _quotation_from_dict(quotation_dict)
    except (TypeError, ValueError) as exc:
        raise HTTPException(500, f"Stored review data is malformed: {exc}") from exc

    acknowledged_indices = set(repo.load_requirements_acknowledged(review_id))
    acknowledged_requirements = [
        req
        for idx, req in enumerate(anfrage.anforderungen)
        if idx in acknowledged_indices
    ]

    workflow = load_user_settings().workflow
    style_hint = workflow.llm_email_body_style_hint or ""

    pipeline = _common.get_pipeline()
    llm = build_llm(pipeline.settings)
    model_name = (
        pipeline.settings.gemini_model
        if pipeline.settings.llm_provider == "gemini"
        else pipeline.settings.azure_model
    )

    try:
        body, language = generate_reply_body(
            anfrage=anfrage,
            quotation=quotation,
            mail_body=str(mail.get("body") or ""),
            style_hint=style_hint,
            llm=llm,
            acknowledged_requirements=acknowledged_requirements,
            usage_callback=lambda usage: repo.record_llm_usage(
                review_id,
                source="reply_body",
                usage=usage,
                model=model_name,
            ),
        )
    except Exception as exc:
        raise HTTPException(503, f"Reply-body generation failed: {exc}") from exc

    return ReplyBodyResponse(body=body, language=language, model=model_name)


@router.post("/reviews/{review_id}/finalize", response_model=FinalizeResponse)
def finalize_quotation(review_id: str, payload: FinalizeRequest) -> dict:
    _common.require_review(review_id)
    return _common.run_use_case(
        lambda: _workflow_service().finalize_quotation(
            review_id,
            actor=payload.actor,
            filename=payload.filename,
            warning_acknowledged=payload.warning_acknowledged,
            exception_reason=payload.exception_reason,
        )
    )
