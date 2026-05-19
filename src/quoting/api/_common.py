"""Shared dependencies for the frontend router and its sub-routers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from quoting.pipeline import QuotingPipeline
from quoting.reviews import default_artifact_root, get_default_repository
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = default_artifact_root()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_pipeline: QuotingPipeline | None = None


def get_pipeline() -> QuotingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = QuotingPipeline()
    return _pipeline


def get_review_repo() -> SQLiteReviewRepository:
    return get_default_repository()


def require_review(review_id: str) -> str:
    """Validate ``review_id`` exists and return it. Raises 404 otherwise."""
    if "/" in review_id or "\\" in review_id or review_id in {".", ".."}:
        raise HTTPException(404, f"Review {review_id} not found")
    if not get_default_repository().exists(review_id):
        raise HTTPException(404, f"Review {review_id} not found")
    return review_id


def review_dir(review_id: str) -> Path:
    """Return the on-disk artifact directory for an existing review."""
    require_review(review_id)
    folder = get_default_repository().artifact_dir(review_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".eml": "message/rfc822",
        ".msg": "application/vnd.ms-outlook",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
    }.get(suffix, "application/octet-stream")


def file_response_inline(path: Path) -> FileResponse:
    return FileResponse(
        path,
        media_type=guess_media_type(path),
        filename=path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )
