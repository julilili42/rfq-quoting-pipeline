"""Upload-driven review creation."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from quoting.api import _common
from quoting.api.services.review_service import build_mail
from quoting.ingestion import detect_file_type

_ALLOWED_UPLOAD_TYPES = {"pdf", "xlsx", "csv", "eml", "msg"}


async def create_review_from_upload(file: UploadFile) -> str:
    """Persist the uploaded file as a new review and run the pipeline.

    Returns the new ``review_id``. Raises ``HTTPException`` on validation
    failure or pipeline error.
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

    _common.get_container().progress_store(repo).init(review_id)

    target = folder / safe_name
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    repo.register_document(
        review_id,
        kind="attachment",
        path=target,
        filename=safe_name,
        content_type=file.content_type,
    )

    repo.save_mail(
        review_id,
        {
            "subject": Path(file.filename).stem,
            "from": "",
            "body": "",
            "attachments": [{"name": safe_name}],
        },
    )

    try:
        mail = build_mail(target)
        result = _common.get_pipeline().run(
            mail,
            output_dir=_common.REVIEW_DIR,
            work_name=review_id,
            snapshot_sink=lambda name, data: repo.save_payload(review_id, name, data),
        )
        repo.register_document(
            review_id,
            kind="draft_pdf",
            path=result.pdf_path,
            filename=result.pdf_path.name,
            content_type="application/pdf",
        )
    except Exception as exc:
        raise HTTPException(500, f"Pipeline failed: {exc}") from exc

    return review_id
