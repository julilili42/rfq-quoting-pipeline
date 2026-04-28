from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api.progress_store import (
    complete_progress,
    fail_progress,
    init_progress,
    read_progress,
    update_step,
)
from quoting.ingestion import Mail
from quoting.pipeline import QuotingPipeline, StepProgress

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"
TUNNEL_FILE = PROJECT_ROOT / ".tunnel_url"

STREAMLIT_BASE_URL = os.getenv("STREAMLIT_BASE_URL", "http://localhost:8501")


def _api_base_url() -> str:
    """
    Resolve the public base URL the add-in should hit.

    Priority:
    1. <project>/.tunnel_url written by run_review_api.py at runtime
    2. API_BASE_URL from environment
    3. http://127.0.0.1:8000
    """
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


@app.get("/health")
def health():
    return {
        "ok": True,
        "api_base_url": _api_base_url(),
        "streamlit_base_url": STREAMLIT_BASE_URL,
    }


@app.post("/api/reviews")
def create_review(
    payload: MailReviewRequest,
    background_tasks: BackgroundTasks,
):
    review_id = uuid.uuid4().hex[:12]
    folder = REVIEW_DIR / review_id
    folder.mkdir(parents=True, exist_ok=True)

    init_progress(folder, review_id)

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


@app.get("/api/reviews/{review_id}/pdf")
def get_review_pdf(review_id: str):
    folder = REVIEW_DIR / review_id

    if not folder.exists():
        raise HTTPException(404, f"Review {review_id} not found")

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
        result = _pipeline.run(
            mail,
            output_dir=folder,
            work_name="pipeline",
            progress=on_progress,
        )

        api_base = _api_base_url()

        response = {
            "review_id": review_id,
            "review_url": f"{STREAMLIT_BASE_URL}?review_id={review_id}",
            "draft_pdf_url": f"{api_base}/api/reviews/{review_id}/pdf",
            "draft_pdf_filename": f"Angebot_Draft_{review_id}.pdf",
            "status_url": f"{api_base}/api/reviews/{review_id}/status",
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
        filename=f"Angebot_Draft_{review_id}.pdf",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )