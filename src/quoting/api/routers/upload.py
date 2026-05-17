"""POST /reviews/upload — create a new review from an uploaded file."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from quoting.api.services.upload_service import create_review_from_upload

router = APIRouter()


@router.post("/reviews/upload")
async def upload_review(file: Annotated[UploadFile, File()]) -> dict:
    review_id = await create_review_from_upload(file)
    return {"review_id": review_id}
