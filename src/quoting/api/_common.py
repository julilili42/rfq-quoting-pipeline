"""Shared dependencies for the frontend router and its sub-routers.

Keeping ``REVIEW_DIR`` and the cached ``QuotingPipeline`` here lets every
sub-router agree on the same configuration, and lets tests monkeypatch a
single location.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from quoting.pipeline import QuotingPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_pipeline: QuotingPipeline | None = None


def get_pipeline() -> QuotingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = QuotingPipeline()
    return _pipeline


def review_dir(review_id: str) -> Path:
    root = REVIEW_DIR.resolve()
    folder = (REVIEW_DIR / review_id).resolve()
    try:
        folder.relative_to(root)
    except ValueError as exc:
        raise HTTPException(404, f"Review {review_id} not found") from exc
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(404, f"Review {review_id} not found")
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
