from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api import _common
from quoting.api.container import get_app_container
from quoting.api.frontend_router import router as frontend_router
from quoting.api.job_worker import JobWorker
from quoting.api.services.review_workflow_service import (
    ReviewWorkflowService,
)
from quoting.api.settings_store import (
    AppSettings,
)
from quoting.api.settings_store import (
    load_settings as load_app_settings,
)
from quoting.api.settings_store import (
    save_settings as save_app_settings,
)
from quoting.api.use_cases.dtos import IncomingMailAttachment, IncomingMailReview
from quoting.reviews import api_base_url

log = logging.getLogger("quoting.api")

STREAMLIT_BASE_URL = os.getenv("STREAMLIT_BASE_URL", "http://localhost:8501")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the pipeline job worker for the lifetime of the app.

    The worker pulls jobs off the SQLite queue and dispatches them to
    the per-step handlers exposed by the :class:`PipelineCoordinator`.
    On shutdown it's stopped cleanly so the next process start sees a
    consistent queue.
    """
    container = get_app_container()
    coordinator = container.pipeline_coordinator()
    worker = JobWorker(
        queue=container.job_queue(),
        handlers=coordinator.worker_handlers(),
    )
    worker.start()
    app.state.job_worker = worker
    log.info("JobWorker started")
    try:
        yield
    finally:
        worker.stop(timeout=5.0)
        log.info("JobWorker stopped")


app = FastAPI(title="Quoting Pipeline API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(frontend_router)


# --------------------------------------------------------- request payloads
class MailAttachment(BaseModel):
    name: str
    contentType: str | None = None
    size: int | None = None
    id: str | None = None
    contentBase64: str | None = None


class MailReviewRequest(BaseModel):
    model_config = {"populate_by_name": True}
    subject: str
    sender: str = Field(alias="from")
    body: str
    attachments: list[MailAttachment] = []
    outlook_item_id: str | None = None


class ApprovalTransitionRequest(BaseModel):
    target: str
    actor: str | None = None
    warning_acknowledged: bool | None = None
    exception_reason: str | None = None
    changed_fields: list[str] | None = None


# --------------------------------------------------------- health & settings
@app.get("/health")
def health():
    return {
        "ok": True,
        "api_base_url": api_base_url(),
        "streamlit_base_url": STREAMLIT_BASE_URL,
    }


@app.get("/api/settings")
def get_settings():
    return load_app_settings().to_dict()


@app.put("/api/settings")
def put_settings(payload: dict):
    settings = AppSettings.from_dict(payload)
    save_app_settings(settings)
    return settings.to_dict()


# --------------------------------------------------------- review lifecycle
def _workflow_service() -> ReviewWorkflowService:
    return _common.get_review_workflow_service(
        review_ui_base_url=STREAMLIT_BASE_URL,
    )


@app.post("/api/reviews")
def create_review(payload: MailReviewRequest):
    service = _workflow_service()
    return _common.run_use_case(
        lambda: service.create_review_from_mail(_mail_review_input(payload))
    )


@app.get("/api/reviews/{review_id}/status")
def get_review_status(review_id: str):
    _common.require_review(review_id)
    return _workflow_service().get_progress(review_id)


@app.get("/api/reviews/{review_id}/approval")
def get_approval(review_id: str):
    _common.require_review(review_id)
    return _workflow_service().get_approval(review_id)


@app.post("/api/reviews/{review_id}/approval")
def post_approval(review_id: str, payload: ApprovalTransitionRequest):
    _common.require_review(review_id)
    return _workflow_service().transition_approval(
        review_id,
        target=payload.target,
        actor=payload.actor,
        changed_fields=payload.changed_fields,
        warning_acknowledged=payload.warning_acknowledged,
        exception_reason=payload.exception_reason,
    )


@app.post("/api/reviews/{review_id}/reset")
def reset_review(review_id: str):
    """Reset a review and re-run the pipeline against the saved mail."""
    _common.require_review(review_id)
    return _common.run_use_case(lambda: _workflow_service().reset_review(review_id))


# --------------------------------------------------------------- PDF endpoints
@app.get("/api/reviews/{review_id}/pdf")
def get_review_pdf(review_id: str):
    """Return the most appropriate PDF — final if approved, else draft."""
    _common.require_review(review_id)
    pdf, _ = _common.get_review_read_service().find_current_pdf(review_id)
    if pdf is None:
        raise HTTPException(404, "PDF not generated for this review")
    return _pdf_response(pdf, review_id)


@app.get("/api/reviews/{review_id}/pdf/draft")
def get_review_draft_pdf(review_id: str):
    """Always return the draft PDF (with the red AI warning banner)."""
    _common.require_review(review_id)
    pdf = _common.get_review_read_service().find_draft_pdf(review_id)
    if pdf is None:
        raise HTTPException(404, "Draft PDF not generated for this review")
    return _pdf_response(pdf, review_id, suffix="draft")


@app.get("/api/reviews/{review_id}/pdf/final")
def get_review_final_pdf(review_id: str):
    """Return the final PDF — only available after the user approves."""
    _common.require_review(review_id)
    pdf = _common.get_review_read_service().find_final_pdf(review_id)
    if pdf is None:
        raise HTTPException(
            404,
            "Final PDF not yet produced — approve the review first",
        )
    return _pdf_response(pdf, review_id, suffix="final")


# --------------------------------------------------------- internals
def _mail_review_input(payload: MailReviewRequest) -> IncomingMailReview:
    return IncomingMailReview(
        subject=payload.subject,
        sender=payload.sender,
        body=payload.body,
        attachments=[
            IncomingMailAttachment(
                name=attachment.name,
                content_type=attachment.contentType,
                size=attachment.size,
                id=attachment.id,
                content_base64=attachment.contentBase64,
            )
            for attachment in payload.attachments
        ],
        outlook_item_id=payload.outlook_item_id,
    )


def _pdf_response(pdf: Path, review_id: str, *, suffix: str | None = None) -> FileResponse:
    if suffix:
        filename = f"Angebot_{review_id}_{suffix.upper()}.pdf"
    else:
        filename = f"Angebot_{review_id}.pdf"

    return FileResponse(
        pdf,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )
