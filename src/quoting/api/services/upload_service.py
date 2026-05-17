"""Upload-driven review creation."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from quoting.api import _common
from quoting.api.progress_store import init_progress
from quoting.api.services.review_service import build_mail
from quoting.ingestion import detect_file_type
from quoting.reviews import ReviewFiles, write_json

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
    folder = _common.REVIEW_DIR / review_id
    folder.mkdir(parents=True, exist_ok=True)

    init_progress(folder, review_id)

    target = folder / safe_name
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    write_json(
        folder / ReviewFiles.MAIL,
        {
            "subject": Path(file.filename).stem,
            "from": "",
            "body": "",
            "attachments": [{"name": safe_name}],
        },
    )

    try:
        mail = build_mail(target)
        _common.get_pipeline().run(mail, output_dir=_common.REVIEW_DIR, work_name=review_id)
    except Exception as exc:
        raise HTTPException(500, f"Pipeline failed: {exc}") from exc

    return review_id
