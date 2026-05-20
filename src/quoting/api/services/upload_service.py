"""Upload-driven review creation."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

from quoting.api import _common
from quoting.ingestion import Mail, detect_file_type, parse_mail
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

_ALLOWED_UPLOAD_TYPES = {"pdf", "xlsx", "csv", "eml", "msg"}


async def create_review_from_upload(file: UploadFile) -> str:
    """Persist the uploaded file as a new review and enqueue the pipeline.

    Returns the new ``review_id``. Raises ``HTTPException`` on validation
    failure or upload preparation error.
    """
    if not file.filename:
        raise HTTPException(400, "Uploaded file is missing a filename")

    contents = await file.read()
    if len(contents) > _common.MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large: max {_common.MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    await file.seek(0)

    safe_name = Path(file.filename).name
    file_type = detect_file_type(Path(safe_name))
    if file_type not in _ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type '{file_type}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_UPLOAD_TYPES))}",
        )

    review_id = uuid.uuid4().hex[:12]
    repo = _common.get_review_repo()
    repo.create_review(review_id, subject=Path(file.filename).stem, source="upload")
    folder = repo.artifact_dir(review_id)
    folder.mkdir(parents=True, exist_ok=True)

    container = _common.get_container()
    progress_store = container.progress_store(repo)
    progress_store.init(review_id)

    target = folder / safe_name
    try:
        target.write_bytes(contents)
        mail = _persist_uploaded_input(
            repo=repo,
            review_id=review_id,
            target=target,
            file_type=file_type,
            upload_content_type=file.content_type,
            fallback_subject=Path(file.filename).stem,
        )
        if not mail.has_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file has neither body text nor supported attachments.",
            )
        progress_store.update_step(
            review_id,
            "Mail vorbereiten",
            "completed",
            "Upload gespeichert",
        )
    except HTTPException as exc:
        progress_store.fail(review_id, str(exc.detail))
        raise
    except Exception as exc:
        progress_store.fail(review_id, str(exc))
        raise HTTPException(400, f"Could not prepare upload: {exc}") from exc

    container.pipeline_coordinator().start_pipeline(review_id)

    return review_id


def _persist_uploaded_input(
    *,
    repo: SQLiteReviewRepository,
    review_id: str,
    target: Path,
    file_type: str,
    upload_content_type: str | None,
    fallback_subject: str,
) -> Mail:
    if file_type in {"eml", "msg"}:
        repo.register_document(
            review_id,
            kind="original",
            path=target,
            filename=target.name,
            content_type=upload_content_type or _common.guess_media_type(target),
        )
        mail = parse_mail(target, repo.artifact_dir(review_id))
        for attachment in mail.attachments:
            repo.register_document(
                review_id,
                kind="attachment",
                path=attachment,
                filename=attachment.name,
                content_type=_common.guess_media_type(attachment),
            )
        repo.save_mail(
            review_id,
            _mail_payload(
                subject=mail.subject or fallback_subject,
                sender=mail.sender,
                body=mail.body,
                attachments=mail.attachments,
            ),
        )
        return mail

    repo.register_document(
        review_id,
        kind="attachment",
        path=target,
        filename=target.name,
        content_type=upload_content_type or _common.guess_media_type(target),
    )
    mail = Mail(
        subject=fallback_subject,
        sender="",
        body="",
        attachments=[target],
    )
    repo.save_mail(
        review_id,
        _mail_payload(
            subject=mail.subject,
            sender=mail.sender,
            body=mail.body,
            attachments=mail.attachments,
        ),
    )
    return mail


def _mail_payload(
    *,
    subject: str,
    sender: str,
    body: str,
    attachments: list[Path],
) -> dict[str, Any]:
    return {
        "subject": subject,
        "from": sender,
        "body": body,
        "attachments": [_attachment_meta(path) for path in attachments],
    }


def _attachment_meta(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "name": path.name,
        "contentType": _common.guess_media_type(path),
    }
    try:
        meta["size"] = path.stat().st_size
    except OSError:
        pass
    return meta
