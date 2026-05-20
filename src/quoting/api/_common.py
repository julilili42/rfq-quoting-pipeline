"""Shared dependencies for the frontend router and its sub-routers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from fastapi import HTTPException
from fastapi.responses import FileResponse

from quoting.api.container import AppContainer, get_app_container
from quoting.api.use_cases.errors import (
    UseCaseBadRequest,
    UseCaseConflict,
    UseCaseError,
    UseCaseFailure,
    UseCaseUnprocessable,
)
from quoting.pipeline import QuotingPipeline
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.services.review_read_service import ReviewReadService
    from quoting.api.services.review_workflow_service import ReviewWorkflowService

PROJECT_ROOT = Path(__file__).resolve().parents[3]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

T = TypeVar("T")


def get_container() -> AppContainer:
    return get_app_container()


def get_pipeline() -> QuotingPipeline:
    return get_container().pipeline()


def get_review_repo() -> SQLiteReviewRepository:
    return get_container().review_repo()


def get_review_workflow_service(
    *,
    pipeline: QuotingPipeline | None = None,
    **kwargs: Any,
) -> ReviewWorkflowService:
    return get_container().review_workflow_service(
        pipeline=pipeline or get_pipeline(),
        **kwargs,
    )


def get_review_read_service() -> ReviewReadService:
    return get_container().review_read_service()


def raise_http_for_use_case_error(exc: UseCaseError) -> None:
    status_code = {
        UseCaseBadRequest: 400,
        UseCaseConflict: 409,
        UseCaseUnprocessable: 422,
        UseCaseFailure: 500,
    }.get(type(exc), 500)
    raise HTTPException(status_code=status_code, detail=exc.detail) from exc


def run_use_case(action: Callable[[], T]) -> T:
    try:
        return action()
    except UseCaseError as exc:
        raise_http_for_use_case_error(exc)
        raise


def require_review(review_id: str) -> str:
    """Validate ``review_id`` exists and return it. Raises 404 otherwise."""
    if "/" in review_id or "\\" in review_id or review_id in {".", ".."}:
        raise HTTPException(404, f"Review {review_id} not found")
    if not get_review_repo().exists(review_id):
        raise HTTPException(404, f"Review {review_id} not found")
    return review_id


def review_dir(review_id: str) -> Path:
    """Return the on-disk artifact directory for an existing review."""
    require_review(review_id)
    folder = get_review_repo().artifact_dir(review_id)
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
