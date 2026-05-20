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
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline

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


@router.get("/reviews/by-outlook-item/{outlook_item_id}")
def get_review_by_outlook_item(outlook_item_id: str) -> dict:
    """Compact status payload for the review bound to ``outlook_item_id``.

    Used by the Outlook add-in to render the right workflow card without
    keeping any state in localStorage. 404 when no review is bound.
    """
    status = _workflow_service().get_outlook_item_status(outlook_item_id)
    if status is None:
        raise HTTPException(404, f"No review bound to Outlook item {outlook_item_id}")
    return status


@router.post("/reviews/by-outlook-item/{outlook_item_id}/detach", status_code=204)
def detach_outlook_item(outlook_item_id: str) -> Response:
    """Unlink the review currently bound to ``outlook_item_id``.

    The review is preserved (still reachable via the overview); the
    Outlook plugin reverts to "new" for this mail.
    """
    _workflow_service().detach_outlook_item(outlook_item_id)
    return Response(status_code=204)


@router.post("/reviews/{review_id}/mark-opened")
def mark_review_opened(review_id: str) -> dict:
    """Record the first time the Review-UI was opened for ``review_id``."""
    _common.require_review(review_id)
    return _workflow_service().mark_review_opened(review_id)


@router.get("/reviews/{review_id}", response_model=ReviewDetail)
def get_review_detail(review_id: str) -> dict:
    _common.require_review(review_id)
    return _workflow_service().get_detail(review_id)


@router.delete("/reviews/{review_id}", status_code=204)
def delete_review(review_id: str) -> Response:
    _common.require_review(review_id)
    _workflow_service().delete_review(review_id)
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
    return _workflow_service().update_anfrage(review_id, payload)


@router.put("/reviews/{review_id}/overrides", response_model=list[ManualOverridePayload])
def put_overrides(review_id: str, payload: list[dict]) -> list[dict]:
    _common.require_review(review_id)
    return _workflow_service().save_overrides(review_id, payload)


@router.post("/reviews/{review_id}/regenerate", response_model=QuotationModel)
def regenerate_quotation(review_id: str) -> dict:
    _common.require_review(review_id)
    return _workflow_service().regenerate_quotation(review_id)


class FinalizeRequest(BaseModel):
    actor: str = Field(min_length=1)
    filename: str | None = None
    warning_acknowledged: bool = False
    exception_reason: str | None = Field(default=None, max_length=1000)


@router.post("/reviews/{review_id}/finalize", response_model=FinalizeResponse)
def finalize_quotation(review_id: str, payload: FinalizeRequest) -> dict:
    _common.require_review(review_id)
    return _workflow_service().finalize_quotation(
        review_id,
        actor=payload.actor,
        filename=payload.filename,
        warning_acknowledged=payload.warning_acknowledged,
        exception_reason=payload.exception_reason,
    )
