from __future__ import annotations

import base64
import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api.approval_store import (
    VALID_TRANSITIONS,
    load_approval,
    reset_approval,
    transition,
)
from quoting.api.progress_store import (
    complete_progress,
    fail_progress,
    init_progress,
    read_progress,
    update_step,
)
from quoting.api.settings_store import (
    AppSettings,
    load_settings as load_app_settings,
    save_settings as save_app_settings,
)
from quoting.ingestion import Mail
from quoting.pipeline import QuotingPipeline, StepProgress
from quoting.reviews import (
    api_base_url,
    find_current_pdf,
    find_draft_pdf,
    find_final_pdf,
    reset_review_artifacts,
    saved_attachment_paths,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"

STREAMLIT_BASE_URL = os.getenv("STREAMLIT_BASE_URL", "http://localhost:8501")


app = FastAPI(title="Quoting Pipeline API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline = QuotingPipeline()


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


class ApprovalTransitionRequest(BaseModel):
    target: str
    actor: str | None = None
    warning_acknowledged: bool | None = None
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
@app.post("/api/reviews")
def create_review(
    payload: MailReviewRequest,
    background_tasks: BackgroundTasks,
):
    review_id = uuid.uuid4().hex[:12]
    folder = REVIEW_DIR / review_id
    folder.mkdir(parents=True, exist_ok=True)

    init_progress(folder, review_id)
    reset_approval(folder)

    try:
        mail = _prepare_mail_payload(payload=payload, folder=folder)
        update_step(
            folder,
            "Mail vorbereiten",
            "completed",
            "Mail und Anhänge gespeichert",
        )
    except HTTPException:
        raise
    except Exception as exc:
        fail_progress(folder, str(exc))
        raise HTTPException(400, f"Could not prepare mail: {exc}") from exc

    background_tasks.add_task(
        _run_review_pipeline,
        review_id,
        folder,
        mail,
    )

    return _build_review_response(review_id, status="running")


@app.get("/api/reviews/{review_id}/status")
def get_review_status(review_id: str):
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")
    progress = read_progress(folder)
    if progress is None:
        raise HTTPException(404, f"Progress for review {review_id} not found")
    return progress


@app.get("/api/reviews/{review_id}/approval")
def get_approval(review_id: str):
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")
    return load_approval(folder).to_dict()


@app.post("/api/reviews/{review_id}/approval")
def post_approval(review_id: str, payload: ApprovalTransitionRequest):
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")
    if payload.target not in {"draft_generated", "reviewed", "approved", "ready_to_send"}:
        raise HTTPException(400, f"Unknown target state: {payload.target}")
    record = transition(
        folder,
        target=payload.target,  # type: ignore[arg-type]
        actor=payload.actor,
        changed_fields=payload.changed_fields,
        warning_acknowledged=payload.warning_acknowledged,
    )
    return record.to_dict()


@app.post("/api/reviews/{review_id}/reset")
def reset_review(review_id: str, background_tasks: BackgroundTasks):
    """Reset a review and re-run the pipeline against the saved mail."""
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

    reset_review_artifacts(folder, review_id)

    mail = _rehydrate_mail_from_disk(folder)
    background_tasks.add_task(
        _run_review_pipeline,
        review_id,
        folder,
        mail,
    )

    base = api_base_url()
    return {
        "review_id": review_id,
        "status": "running",
        "status_url": f"{base}/api/reviews/{review_id}/status",
    }


# --------------------------------------------------------------- PDF endpoints
#
# Three explicit endpoints so the Streamlit UI's iframe sees three distinct
# URLs depending on what it wants to display. Previously a single endpoint
# served both draft and final, which combined with base64 data-URL embedding
# in the UI confused the browser into reusing the same iframe content for
# both tabs.
@app.get("/api/reviews/{review_id}/pdf")
def get_review_pdf(review_id: str):
    """Return the most appropriate PDF — final if approved, else draft."""
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

    pdf, _ = find_current_pdf(folder, review_id)
    if pdf is None:
        raise HTTPException(404, "PDF not generated for this review")
    return _pdf_response(pdf, review_id)


@app.get("/api/reviews/{review_id}/pdf/draft")
def get_review_draft_pdf(review_id: str):
    """Always return the draft PDF (with the red AI warning banner)."""
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

    pdf = find_draft_pdf(folder, review_id)
    if pdf is None:
        raise HTTPException(404, "Draft PDF not generated for this review")
    return _pdf_response(pdf, review_id, suffix="draft")


@app.get("/api/reviews/{review_id}/pdf/final")
def get_review_final_pdf(review_id: str):
    """Return the final PDF — only available after the user approves."""
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

    pdf = find_final_pdf(folder, review_id)
    if pdf is None:
        raise HTTPException(
            404,
            "Final PDF not yet produced — approve the review first",
        )
    return _pdf_response(pdf, review_id, suffix="final")


# --------------------------------------------------------- internals
def _build_review_response(review_id: str, *, status: str) -> dict:
    base = api_base_url()
    return {
        "review_id": review_id,
        "review_url": f"{STREAMLIT_BASE_URL}?review_id={review_id}",
        "draft_pdf_url": f"{base}/api/reviews/{review_id}/pdf/draft",
        "draft_pdf_filename": f"Angebot_Draft_{review_id}.pdf",
        "final_pdf_url": f"{base}/api/reviews/{review_id}/pdf/final",
        "final_pdf_filename": f"Angebot_{review_id}_FINAL.pdf",
        "status_url": f"{base}/api/reviews/{review_id}/status",
        "approval_url": f"{base}/api/reviews/{review_id}/approval",
        "status": status,
    }


def _prepare_mail_payload(payload: MailReviewRequest, folder: Path) -> Mail:
    meta = payload.model_dump(by_alias=True, exclude={"attachments"})
    meta["attachments"] = [
        {
            key: value
            for key, value in attachment.model_dump().items()
            if key != "contentBase64"
        }
        for attachment in payload.attachments
    ]
    (folder / "mail.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    saved_paths: list[Path] = []
    for attachment in payload.attachments:
        if not attachment.contentBase64:
            continue
        safe_name = Path(attachment.name).name or f"attachment_{len(saved_paths)}"
        target = folder / safe_name
        try:
            target.write_bytes(base64.b64decode(attachment.contentBase64))
        except Exception as exc:
            raise HTTPException(
                400,
                f"Bad base64 in attachment '{attachment.name}': {exc}",
            ) from exc
        saved_paths.append(target)

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


def _rehydrate_mail_from_disk(folder: Path) -> Mail:
    """Rebuild a Mail from a persisted review folder for resets."""
    meta_path = folder / "mail.json"
    if not meta_path.exists():
        raise HTTPException(400, "No mail.json — review cannot be reset")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse mail.json: {exc}") from exc

    attachments_meta = meta.get("attachments") or []
    attachment_paths: list[Path] = []
    for entry in attachments_meta:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        path = folder / Path(name).name
        if path.exists():
            attachment_paths.append(path)

    mail = Mail(
        subject=str(meta.get("subject") or ""),
        sender=str(meta.get("from") or meta.get("sender") or ""),
        body=str(meta.get("body") or ""),
        attachments=attachment_paths,
    )
    if not mail.has_content:
        raise HTTPException(
            400,
            "Reset failed: mail has no body and no attachments on disk.",
        )
    return mail


def _run_review_pipeline(
    review_id: str,
    folder: Path,
    mail: Mail,
) -> None:
    def on_progress(progress: StepProgress) -> None:
        update_step(
            review_dir=folder,
            step_name=progress.step_name,
            status=progress.status,
            detail=progress.detail,
        )

    try:
        # Initial pipeline run is always a draft (with red warning).
        # Final/approved PDFs get re-rendered later by the UI.
        result = _pipeline.run(
            mail,
            output_dir=folder,
            work_name="pipeline",
            progress=on_progress,
            is_final=False,
        )
        response = _build_review_response(review_id, status="completed")
        response["summary"] = result.summary()
        complete_progress(folder, response)
    except Exception as exc:
        fail_progress(folder, str(exc))


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
