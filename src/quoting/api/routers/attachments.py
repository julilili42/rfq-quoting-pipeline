"""Attachment serving, PDF highlight resolution, and tabular previews."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api import _common
from quoting.reviews import get_default_repository
from quoting.reviews.source_highlights import (
    HighlightResult,
    TargetKind,
    resolve_pdf_highlight,
)

log = logging.getLogger("quoting.frontend_router")

router = APIRouter()


_PREVIEW_ROW_CAP = 500


def _resolve_review_attachment(review_id: str, filename: str) -> Path:
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise HTTPException(400, "Invalid filename")

    doc = get_default_repository().current_document(
        review_id, kind="attachment", filename=safe_name
    )
    path = _document_path(doc)
    if path is None:
        raise HTTPException(404, f"Attachment '{safe_name}' not found")
    return path


class PdfHighlightRequest(BaseModel):
    source_page: int | None = None
    source_quote: str | None = None
    candidates: list[str] = Field(default_factory=list)
    target_kind: TargetKind = "generic"


class PdfHighlightArea(BaseModel):
    pageIndex: int
    left: float
    top: float
    width: float
    height: float


class PdfHighlightResponse(BaseModel):
    status: str
    areas: list[PdfHighlightArea]
    pageIndex: int | None = None
    matched_text: str | None = None
    message: str | None = None


def _pdf_highlight_response(result: HighlightResult) -> PdfHighlightResponse:
    return PdfHighlightResponse(
        status=result.status,
        areas=[PdfHighlightArea(**area.__dict__) for area in result.areas],
        pageIndex=result.pageIndex,
        matched_text=result.matched_text,
        message=result.message,
    )


@router.get("/reviews/{review_id}/attachment/{filename}")
def get_review_attachment(review_id: str, filename: str) -> FileResponse:
    _common.require_review(review_id)
    return _common.file_response_inline(_resolve_review_attachment(review_id, filename))


@router.post(
    "/reviews/{review_id}/attachment/{filename}/pdf/highlight",
    response_model=PdfHighlightResponse,
)
def get_pdf_source_highlight(
    review_id: str,
    filename: str,
    payload: PdfHighlightRequest,
) -> PdfHighlightResponse:
    _common.require_review(review_id)
    path = _resolve_review_attachment(review_id, filename)
    if path.suffix.lower() != ".pdf":
        raise HTTPException(415, "Attachment is not a PDF")

    result = resolve_pdf_highlight(
        path,
        source_page=payload.source_page,
        source_quote=payload.source_quote,
        candidates=payload.candidates,
        target_kind=payload.target_kind,
    )
    return _pdf_highlight_response(result)


@router.get("/reviews/{review_id}/original")
def get_review_original(review_id: str) -> FileResponse:
    _common.require_review(review_id)

    supported = {".pdf", ".msg", ".eml", ".xlsx", ".xls", ".csv", ".tsv"}
    candidate = next(
        (
            path
            for path in _original_document_paths(review_id)
            if path.suffix.lower() in supported
        ),
        None,
    )
    if candidate is None:
        raise HTTPException(404, "No original input file found for this review")
    return _common.file_response_inline(candidate)


class TablePreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    truncated: bool
    sheet_names: list[str] = Field(default_factory=list)
    active_sheet: str | None = None


def _find_tabular_original(review_id: str) -> Path | None:
    supported = {".csv", ".tsv", ".xlsx", ".xls"}
    return next(
        (
            path
            for path in _original_document_paths(review_id)
            if path.suffix.lower() in supported
        ),
        None,
    )


def _document_path(doc: dict[str, Any] | None) -> Path | None:
    if not doc:
        return None
    path = Path(str(doc.get("storage_path") or ""))
    if path.exists() and path.is_file():
        return path
    return None


def _original_document_paths(review_id: str) -> list[Path]:
    repo = get_default_repository()
    paths: list[Path] = []
    for kind in ("attachment", "original"):
        for doc in repo.list_documents(review_id, kind=kind):
            path = _document_path(doc)
            if path is not None:
                paths.append(path)
    return paths


def _normalise_cell(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, (str, int, bool)) or value is None:
        return value

    return str(value)


def _df_to_preview(df: Any) -> TablePreview:
    total = int(len(df))
    truncated = total > _PREVIEW_ROW_CAP
    head = df.head(_PREVIEW_ROW_CAP)

    columns = [str(c) for c in head.columns]
    rows: list[dict[str, Any]] = []

    for _, raw in head.iterrows():
        row: dict[str, Any] = {}
        for col in columns:
            row[col] = _normalise_cell(raw[col])
        rows.append(row)

    return TablePreview(
        columns=columns,
        rows=rows,
        total_rows=total,
        truncated=truncated,
    )


def _csv_preview(path: Path, suffix: str) -> TablePreview:
    import pandas as pd

    candidates = ["\t"] if suffix == ".tsv" else [";", ",", "\t", "|"]
    best_df = None

    for sep in candidates:
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                df = pd.read_csv(
                    path,
                    sep=sep,
                    encoding=enc,
                    engine="python",
                    on_bad_lines="skip",
                )
            except Exception as exc:
                log.debug("csv_preview: sep=%r enc=%r failed for %s: %s", sep, enc, path.name, exc)
                continue

            if best_df is None or len(df.columns) > len(best_df.columns):
                best_df = df

        if best_df is not None and len(best_df.columns) > 1:
            break

    if best_df is None:
        raise ValueError("No separator/encoding combination produced a table")

    return _df_to_preview(best_df)


def _xlsx_preview(path: Path, sheet: str | None) -> TablePreview:
    import pandas as pd

    excel = pd.ExcelFile(path)
    sheet_names = list(excel.sheet_names)
    if not sheet_names:
        raise HTTPException(422, "Excel file contains no sheets")
    active = sheet if sheet in sheet_names else sheet_names[0]

    df = pd.read_excel(excel, sheet_name=active)
    preview = _df_to_preview(df)
    preview.sheet_names = sheet_names
    preview.active_sheet = active

    return preview


@router.get("/reviews/{review_id}/original/preview", response_model=TablePreview)
def preview_original_table(
    review_id: str,
    sheet: str | None = Query(None, description="XLSX sheet name, default: first"),
) -> TablePreview:
    _common.require_review(review_id)
    path = _find_tabular_original(review_id)

    if path is None:
        raise HTTPException(415, "Original is not a tabular file")

    suffix = path.suffix.lower()

    try:
        if suffix in {".xlsx", ".xls"}:
            return _xlsx_preview(path, sheet)
        return _csv_preview(path, suffix)
    except Exception as exc:
        raise HTTPException(422, f"Could not parse {path.name}: {exc}") from exc
