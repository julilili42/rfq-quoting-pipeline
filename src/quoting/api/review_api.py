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

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"
TUNNEL_FILE = PROJECT_ROOT / ".tunnel_url"

STREAMLIT_BASE_URL = os.getenv("STREAMLIT_BASE_URL", "http://localhost:8501")


def _api_base_url() -> str:
    """Resolve the public base URL the add-in should hit."""
    try:
        if TUNNEL_FILE.exists():
            url = TUNNEL_FILE.read_text(encoding="utf-8").strip()
            if url:
                return url.rstrip("/")
    except Exception:
        pass
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


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
        "api_base_url": _api_base_url(),
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

    api_base = _api_base_url()
    return {
        "review_id": review_id,
        "review_url": f"{STREAMLIT_BASE_URL}?review_id={review_id}",
        "draft_pdf_url": f"{api_base}/api/reviews/{review_id}/pdf",
        "draft_pdf_filename": f"Angebot_Draft_{review_id}.pdf",
        "status_url": f"{api_base}/api/reviews/{review_id}/status",
        "approval_url": f"{api_base}/api/reviews/{review_id}/approval",
        "status": "running",
    }


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

    # Wipe pipeline outputs + manual edits but keep the original mail
    # (mail.json + attachments).
    keep = {"mail.json"}
    keep_files = {f for f in folder.iterdir() if f.name in keep}
    saved_attachments = _collect_saved_attachments(folder)

    for entry in folder.iterdir():
        if entry in keep_files:
            continue
        if entry in saved_attachments:
            continue
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
        except Exception:
            pass

    init_progress(folder, review_id)
    reset_approval(folder)

    mail = _rehydrate_mail_from_disk(folder)
    background_tasks.add_task(
        _run_review_pipeline,
        review_id,
        folder,
        mail,
    )

    api_base = _api_base_url()
    return {
        "review_id": review_id,
        "status": "running",
        "status_url": f"{api_base}/api/reviews/{review_id}/status",
    }


@app.get("/api/reviews/{review_id}/pdf")
def get_review_pdf(review_id: str):
    folder = REVIEW_DIR / review_id
    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

    # Prefer final PDF if approval has produced one.
    approval = load_approval(folder)
    if approval.final_pdf_path:
        final_pdf = folder / approval.final_pdf_path
        if final_pdf.exists():
            return _pdf_response(final_pdf, review_id)

    preferred = [
        folder / f"Angebot_Draft_{review_id}.pdf",
        folder / "draft_angebot.pdf",
    ]
    for pdf in preferred:
        if pdf.exists():
            return _pdf_response(pdf, review_id)

    candidates = list(folder.rglob("*_ANGEBOT_DRAFT.pdf"))
    if not candidates:
        raise HTTPException(404, "Draft PDF not generated for this review")
    return _pdf_response(candidates[0], review_id)


# --------------------------------------------------------- internals
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


def _collect_saved_attachments(folder: Path) -> set[Path]:
    """Return the attachment files that should survive a reset."""
    meta_path = folder / "mail.json"
    if not meta_path.exists():
        return set()
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    out: set[Path] = set()
    for entry in meta.get("attachments") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        out.add(folder / Path(name).name)
    return out


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

        api_base = _api_base_url()
        response = {
            "review_id": review_id,
            "review_url": f"{STREAMLIT_BASE_URL}?review_id={review_id}",
            "draft_pdf_url": f"{api_base}/api/reviews/{review_id}/pdf",
            "draft_pdf_filename": f"Angebot_Draft_{review_id}.pdf",
            "status_url": f"{api_base}/api/reviews/{review_id}/status",
            "approval_url": f"{api_base}/api/reviews/{review_id}/approval",
            "status": "completed",
            "summary": result.summary(),
        }
        complete_progress(folder, response)
    except Exception as exc:
        fail_progress(folder, str(exc))


def _pdf_response(pdf: Path, review_id: str) -> FileResponse:
    return FileResponse(
        pdf,
        media_type="application/pdf",
        filename=f"Angebot_{review_id}.pdf",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )
