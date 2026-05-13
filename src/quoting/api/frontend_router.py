"""React frontend endpoints for the review UI.

This router is the single HTTP adapter for the React review frontend.
It includes the former phase-1 endpoints plus the later phase-3 additions:
tabular original preview, ranked stammdaten search, and manual matching.

Wire-up in ``quoting/api/review_api.py``:

    from quoting.api.frontend_router import router as frontend_router
    app.include_router(frontend_router)

Do not include ``frontend_router_phase3`` separately anymore.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import uuid
from datetime import date as _date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api.approval_store import load_approval, transition
from quoting.api.progress_store import init_progress, read_progress
from quoting.api.settings_store import load_user_settings
from quoting.core import Anfrage
from quoting.ingestion import Mail, detect_file_type, mail_from_file, parse_mail
from quoting.matching import MatchResult, match_positions
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline
from quoting.pricing import Quotation, build_quotation
from quoting.reviews import (
    draft_pdf_filename,
    find_draft_pdf,
    find_final_pdf,
    load_mail_meta,
    load_saved_quotation,
    read_json,
    scan_reviews,
    write_json,
)
from quoting.reviews.source_highlights import (
    HighlightResult,
    TargetKind,
    resolve_pdf_highlight,
)
from quoting.ui.review_agent import apply_manual_overrides

log = logging.getLogger("quoting.frontend_router")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

router = APIRouter(prefix="/api", tags=["frontend"])

_pipeline: QuotingPipeline | None = None


def _get_pipeline() -> QuotingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = QuotingPipeline()
    return _pipeline


def _review_dir(review_id: str) -> Path:
    folder = REVIEW_DIR / review_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(404, f"Review {review_id} not found")
    return folder


# ============================================================================
# Reviews: list & detail
# ============================================================================

def _extract_summary_metrics(summary: dict) -> tuple[int, float, float, float]:
    """Return (positions, total_eur, duration_s, match_rate) from a progress summary."""
    positions = int(summary.get("positions") or 0)
    total_eur = float(summary.get("total_eur") or 0.0)
    duration_s = float(summary.get("duration_s") or 0.0)
    matched = (
        int(summary.get("exact") or 0)
        + int(summary.get("fuzzy") or 0)
        + int(summary.get("semantic") or 0)
    )
    match_rate = matched / positions if positions > 0 else 0.0
    return positions, total_eur, duration_s, match_rate


def _accumulate_review_into(folder: Path, progress: dict, agg: dict, per_review: list) -> None:
    """Accumulate one review's metrics into agg and append a row to per_review."""
    agg["total_reviews"] += 1
    if progress.get("status") == "completed":
        agg["completed_reviews"] += 1

    summary = (progress.get("result") or {}).get("summary") or {}
    positions, total_eur, duration_s, match_rate = _extract_summary_metrics(summary)

    agg["total_positions"] += positions
    agg["total_eur"] += total_eur
    if duration_s:
        agg["sum_duration_s"] += duration_s
        agg["reviews_with_duration"] += 1
    if positions:
        agg["sum_match_rate"] += match_rate
        agg["reviews_with_match"] += 1

    token_data = summary.get("token_usage")
    token_row = None
    if isinstance(token_data, dict):
        agg["total_input_tokens"] += int(token_data.get("input_tokens") or 0)
        agg["total_output_tokens"] += int(token_data.get("output_tokens") or 0)
        agg["total_tokens"] += int(token_data.get("total_tokens") or 0)
        agg["reviews_with_token_data"] += 1
        token_row = token_data

    extraction_path = summary.get("extraction_path")
    if extraction_path == "fast_path":
        agg["fast_path_hits"] += 1
    elif extraction_path == "llm":
        agg["llm_calls"] += 1

    per_review.append({
        "review_id": folder.name,
        "subject": str(summary.get("subject") or ""),
        "status": progress.get("status"),
        "updated_at": str(progress.get("updated_at") or ""),
        "positions": positions,
        "match_rate": round(match_rate, 3),
        "total_eur": total_eur,
        "duration_s": duration_s,
        "token_usage": token_row,
        "extraction_path": extraction_path,
    })


def _format_mail_dict(mail_meta: dict) -> dict:
    return {
        "subject": str(mail_meta.get("subject") or ""),
        "from": str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        "body": str(mail_meta.get("body") or ""),
        "attachments": list(mail_meta.get("attachments") or []),
    }


def _upsert_match(matches: list, new_match: MatchResult) -> list:
    """Replace an existing match by pos_nr, or append if not found."""
    updated = []
    replaced = False
    for m in matches:
        if m.pos_nr == new_match.pos_nr:
            updated.append(new_match)
            replaced = True
        else:
            updated.append(m)
    if not replaced:
        updated.append(new_match)
    return updated


@router.get("/metrics")
def get_metrics() -> dict:
    per_review = []
    agg: dict = dict(
        total_reviews=0, completed_reviews=0, total_positions=0,
        total_eur=0.0, sum_duration_s=0.0, sum_match_rate=0.0,
        reviews_with_duration=0, reviews_with_match=0,
        total_input_tokens=0, total_output_tokens=0, total_tokens=0,
        reviews_with_token_data=0,
        fast_path_hits=0, llm_calls=0,
    )

    if not REVIEW_DIR.exists():
        agg.update(avg_duration_s=0.0, avg_match_rate=0.0)
        return {**agg, "per_review": []}

    for folder in sorted(REVIEW_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        progress = read_progress(folder)
        if progress is None:
            continue
        _accumulate_review_into(folder, progress, agg, per_review)

    reviews_with_duration = agg.pop("reviews_with_duration") or 1
    reviews_with_match = agg.pop("reviews_with_match") or 1
    sum_duration_s = agg.pop("sum_duration_s")
    sum_match_rate = agg.pop("sum_match_rate")

    return {
        **agg,
        "avg_duration_s": round(sum_duration_s / reviews_with_duration, 2),
        "avg_match_rate": round(sum_match_rate / reviews_with_match, 3),
        "per_review": per_review,
    }


@router.get("/reviews")
def list_reviews() -> list[dict]:
    summaries = scan_reviews(REVIEW_DIR)
    return [
        {
            "review_id": s.review_id,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "subject": s.subject,
            "sender": s.sender,
            "positions": s.positions,
            "confidence_high": s.confidence_high,
            "confidence_medium": s.confidence_medium,
            "confidence_low": s.confidence_low,
            "matches_exact": s.matches_exact,
            "matches_fuzzy": s.matches_fuzzy,
            "matches_semantic": s.matches_semantic,
            "matches_no_match": s.matches_no_match,
            "total_eur": s.total_eur,
            "currency": s.currency,
            "status": s.status,
            "has_pdf": bool(s.pdf_path),
            "manual_overrides_count": s.manual_overrides_count,
            "extracted_articles": s.extracted_articles,
        }
        for s in summaries
    ]


@router.get("/reviews/{review_id}")
def get_review_detail(review_id: str) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    anfrage = _load_or_extract_anfrage(folder, review_id)
    matches = _load_or_recompute_matches(folder, anfrage, pipeline)
    quotation = _load_quotation(folder)

    overrides = read_json(folder / "manual_overrides.json")
    if not isinstance(overrides, list):
        overrides = []

    mail_meta = load_mail_meta(folder) or {}

    progress = read_progress(folder) or {}

    return {
        "review_id": review_id,
        "created_at": progress.get("created_at"),
        "anfrage": anfrage.model_dump(mode="json"),
        "matches": [m.to_dict() for m in matches],
        "quotation": quotation.to_dict() if quotation else None,
        "manual_overrides": overrides,
        "mail": _format_mail_dict(mail_meta),
        "has_draft_pdf": find_draft_pdf(folder, review_id) is not None,
        "has_final_pdf": find_final_pdf(folder, review_id) is not None,
    }


@router.get("/reviews/{review_id}/mail")
def get_review_mail(review_id: str) -> dict:
    folder = _review_dir(review_id)
    meta = load_mail_meta(folder) or {}

    return _format_mail_dict(meta)


# ============================================================================
# Original input file
# ============================================================================

@router.get("/reviews/{review_id}/attachment/{filename}")
def get_review_attachment(review_id: str, filename: str) -> FileResponse:
    folder = _review_dir(review_id)
    return _file_response_inline(_resolve_review_attachment(folder, filename))


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


@router.post(
    "/reviews/{review_id}/attachment/{filename}/pdf/highlight",
    response_model=PdfHighlightResponse,
)
def get_pdf_source_highlight(
    review_id: str,
    filename: str,
    payload: PdfHighlightRequest,
) -> PdfHighlightResponse:
    folder = _review_dir(review_id)
    path = _resolve_review_attachment(folder, filename)
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


def _resolve_review_attachment(folder: Path, filename: str) -> Path:
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename or safe_name in {".", ".."}:
        raise HTTPException(400, "Invalid filename")

    meta = load_mail_meta(folder) or {}
    allowed = {
        Path(a["name"]).name
        for a in (meta.get("attachments") or [])
        if isinstance(a, dict) and a.get("name")
    }
    if safe_name not in allowed:
        raise HTTPException(404, f"Attachment '{safe_name}' not found")

    candidate = folder / safe_name
    if not candidate.is_file():
        raise HTTPException(404, f"Attachment file '{safe_name}' missing on disk")

    return candidate


def _pdf_highlight_response(result: HighlightResult) -> PdfHighlightResponse:
    return PdfHighlightResponse(
        status=result.status,
        areas=[PdfHighlightArea(**area.__dict__) for area in result.areas],
        pageIndex=result.pageIndex,
        matched_text=result.matched_text,
        message=result.message,
    )


@router.get("/reviews/{review_id}/original")
def get_review_original(review_id: str) -> FileResponse:
    folder = _review_dir(review_id)

    supported = {".pdf", ".msg", ".eml", ".xlsx", ".xls", ".csv", ".tsv"}
    preferred: list[Path] = []
    fallback: list[Path] = []

    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in supported:
            continue

        name = path.name.lower()
        if name.startswith("angebot") or "draft" in name or "_final" in name:
            fallback.append(path)
        else:
            preferred.append(path)

    candidate = next(iter(preferred + fallback), None)
    if candidate is None:
        raise HTTPException(404, "No original input file found for this review")

    return _file_response_inline(candidate)


class TablePreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    truncated: bool
    sheet_names: list[str] = Field(default_factory=list)
    active_sheet: str | None = None


_PREVIEW_ROW_CAP = 500


@router.get("/reviews/{review_id}/original/preview", response_model=TablePreview)
def preview_original_table(
    review_id: str,
    sheet: str | None = Query(None, description="XLSX sheet name, default: first"),
) -> TablePreview:
    folder = _review_dir(review_id)
    path = _find_tabular_original(folder)

    if path is None:
        raise HTTPException(415, "Original is not a tabular file")

    suffix = path.suffix.lower()

    try:
        if suffix in {".xlsx", ".xls"}:
            return _xlsx_preview(path, sheet)
        return _csv_preview(path, suffix)
    except Exception as exc:
        raise HTTPException(422, f"Could not parse {path.name}: {exc}") from exc


def _find_tabular_original(folder: Path) -> Path | None:
    supported = {".csv", ".tsv", ".xlsx", ".xls"}

    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in supported:
            continue

        name = path.name.lower()
        if name.startswith("angebot") or "draft" in name or "_final" in name:
            continue

        return path

    return None


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
            except Exception:
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


# ============================================================================
# Mutations: Anfrage, overrides, regenerate, finalize
# ============================================================================

class AnfragePayload(BaseModel):
    model_config = {"extra": "allow"}


@router.put("/reviews/{review_id}/anfrage")
def put_anfrage(review_id: str, payload: dict) -> dict:
    folder = _review_dir(review_id)

    try:
        anfrage = Anfrage.model_validate(payload)
    except Exception as exc:
        raise HTTPException(400, f"Invalid Anfrage payload: {exc}") from exc

    write_json(folder / "anfrage_reviewed.json", anfrage.model_dump(mode="json"))
    _invalidate_approval(folder)

    return anfrage.model_dump(mode="json")


@router.put("/reviews/{review_id}/overrides")
def put_overrides(review_id: str, payload: list[dict]) -> list[dict]:
    folder = _review_dir(review_id)

    if not isinstance(payload, list):
        raise HTTPException(400, "Overrides payload must be a list")

    write_json(folder / "manual_overrides.json", payload)
    _invalidate_approval(folder)

    return payload


def _load_review_data(
    folder: Path, review_id: str, pipeline: QuotingPipeline
) -> tuple:
    """Load anfrage, matches, and overrides for a review."""
    try:
        anfrage = _load_or_extract_anfrage(folder, review_id)
    except Exception as exc:
        log.exception("load_review_data: anfrage load failed for %s", review_id)
        raise HTTPException(422, f"Anfrage konnte nicht geladen werden: {exc}") from exc

    try:
        matches = _load_or_recompute_matches(folder, anfrage, pipeline)
    except Exception as exc:
        log.exception("load_review_data: match recompute failed for %s", review_id)
        raise HTTPException(422, f"Matching fehlgeschlagen: {exc}") from exc

    overrides = read_json(folder / "manual_overrides.json") or []
    return anfrage, matches, overrides


def _build_quotation_with_overrides(
    anfrage: Anfrage,
    matches: list,
    overrides: list,
    preise_path: Path,
    review_id: str,
) -> Quotation:
    """Build quotation and apply manual overrides."""
    try:
        quotation = build_quotation(anfrage, matches, preise_path)
        if isinstance(overrides, list) and overrides:
            quotation, _ = apply_manual_overrides(quotation, anfrage, overrides, lang="de")
        return quotation
    except Exception as exc:
        log.exception("build_quotation_with_overrides: pricing failed for %s", review_id)
        raise HTTPException(422, f"Preisberechnung fehlgeschlagen: {exc}") from exc


@router.post("/reviews/{review_id}/regenerate")
def regenerate_quotation(review_id: str) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    anfrage, matches, overrides = _load_review_data(folder, review_id, pipeline)
    company_profile = load_user_settings().company
    quotation = _build_quotation_with_overrides(
        anfrage, matches, overrides, pipeline.settings.preise_path, review_id
    )

    pdf_path = folder / draft_pdf_filename(review_id)
    try:
        build_draft_pdf(anfrage, quotation, pdf_path, is_final=False, company_profile=company_profile)
    except Exception as exc:
        log.exception("regenerate: PDF build failed for %s", review_id)
        raise HTTPException(422, f"PDF-Erstellung fehlgeschlagen: {exc}") from exc

    write_json(folder / "quotation_reviewed.json", quotation.to_dict())
    return quotation.to_dict()


class FinalizeRequest(BaseModel):
    actor: str = Field(min_length=1)
    filename: str | None = None


def _sanitize_pdf_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', '_', name.strip())
    name = name.replace(' ', '_')
    name = re.sub(r'_+', '_', name)
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name[:200]


def _resolve_filename_template(template: str, anfrage: Any, review_id: str) -> str:
    def _field(name: str) -> str:
        return (getattr(anfrage, name, '') or '').strip()

    today = _date.today().strftime('%Y%m%d')
    result = (
        template
        .replace('[Kunde]', _field('kunde_firma') or review_id)
        .replace('[Belegnummer]', _field('belegnummer'))
        .replace('[Kundennummer]', _field('kundennummer'))

        .replace('[Ansprechpartner]', _field('kunde_ansprechpartner'))
        .replace('[Datum]', today)
    )
    return _sanitize_pdf_filename(result)


@router.post("/reviews/{review_id}/finalize")
def finalize_quotation(review_id: str, payload: FinalizeRequest) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    anfrage, matches, overrides = _load_review_data(folder, review_id, pipeline)
    user_settings = load_user_settings()
    company_profile = user_settings.company
    quotation = _build_quotation_with_overrides(
        anfrage, matches, overrides, pipeline.settings.preise_path, review_id
    )

    if payload.filename:
        final_filename = _sanitize_pdf_filename(payload.filename)
    else:
        template = user_settings.workflow.final_pdf_filename_template or "Angebot_[Kunde].pdf"
        final_filename = _resolve_filename_template(template, anfrage, review_id)

    final_path = folder / final_filename
    try:
        build_draft_pdf(anfrage, quotation, final_path, is_final=True, company_profile=company_profile)
    except Exception as exc:
        log.exception("finalize: PDF build failed for %s", review_id)
        raise HTTPException(422, f"Final-PDF konnte nicht erstellt werden: {exc}") from exc

    try:
        record = transition(
            folder,
            target="approved",
            actor=payload.actor,
            warning_acknowledged=True,
            final_pdf_path=final_path.name,
        )
    except Exception as exc:
        log.exception("finalize: approval transition failed for %s (PDF was written)", review_id)
        raise HTTPException(500, f"Status-Übergang fehlgeschlagen: {exc}") from exc

    return {"final_pdf_path": record.final_pdf_path or final_path.name}


# ============================================================================
# Upload
# ============================================================================

_ALLOWED_UPLOAD_TYPES = {"pdf", "xlsx", "csv", "eml", "msg"}


@router.post("/reviews/upload")
async def upload_review(file: Annotated[UploadFile, File()]) -> dict:
    if not file.filename:
        raise HTTPException(400, "Uploaded file is missing a filename")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large: max {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    await file.seek(0)

    safe_name = Path(file.filename).name
    file_type = detect_file_type(Path(safe_name))
    if file_type not in _ALLOWED_UPLOAD_TYPES:
        raise HTTPException(415, f"Unsupported file type '{file_type}'. Allowed: {', '.join(sorted(_ALLOWED_UPLOAD_TYPES))}")

    review_id = uuid.uuid4().hex[:12]
    folder = REVIEW_DIR / review_id
    folder.mkdir(parents=True, exist_ok=True)

    init_progress(folder, review_id)

    target = folder / safe_name

    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    write_json(
        folder / "mail.json",
        {
            "subject": Path(file.filename).stem,
            "from": "",
            "body": "",
            "attachments": [{"name": safe_name}],
        },
    )

    try:
        mail = _build_mail(target)
        _get_pipeline().run(mail, output_dir=REVIEW_DIR, work_name=review_id)
    except Exception as exc:
        raise HTTPException(500, f"Pipeline failed: {exc}") from exc

    return {"review_id": review_id}


# ============================================================================
# Stammdaten search & manual re-matching
# ============================================================================

class StammdatenHit(BaseModel):
    artikel_nr: str
    bezeichnung: str
    werkstoff: str | None = None
    abmessungen: str | None = None
    einheit: str = "ST"
    basispreis_eur: float = 0.0
    preis_min_eur: float = 0.0
    preis_max_eur: float = 0.0
    n_offers: int = 0
    sales_group: str | None = None
    material_group: str | None = None
    score: float = 1.0


@router.get("/stammdaten/search", response_model=list[StammdatenHit])
def search_stammdaten(
    q: str = Query("", description="Free-text query"),
    limit: int = Query(25, ge=1, le=100),
) -> list[StammdatenHit]:
    from rapidfuzz import fuzz, process

    query = (q or "").strip()
    pipeline = _get_pipeline()
    records = pipeline.stammdaten_repo.all()

    if not query:
        return [
            _record_to_hit(record, score=1.0)
            for record in sorted(records, key=lambda r: r.artikel_nr)[:limit]
        ]

    if not records:
        return []

    # Exact artikel_nr match — return immediately without fuzzy scoring
    exact = next((r for r in records if r.artikel_nr == query), None)
    if exact:
        return [_record_to_hit(exact, score=1.0)]

    haystack = [
        f"{r.artikel_nr} {r.bezeichnung} {r.werkstoff or ''} {r.abmessungen or ''}".strip()
        for r in records
    ]

    raw_hits = process.extract(
        query,
        haystack,
        scorer=fuzz.token_set_ratio,
        limit=limit,
    )

    hits: list[StammdatenHit] = []

    for _, score, idx in raw_hits:
        if score < 20:
            continue

        hits.append(_record_to_hit(records[idx], score=score / 100.0))

    return hits


def _record_to_hit(record: Any, *, score: float) -> StammdatenHit:
    return StammdatenHit(
        artikel_nr=record.artikel_nr,
        bezeichnung=record.bezeichnung,
        werkstoff=record.werkstoff,
        abmessungen=record.abmessungen,
        einheit=record.einheit,
        basispreis_eur=record.basispreis_eur,
        preis_min_eur=record.preis_min_eur or 0.0,
        preis_max_eur=record.preis_max_eur or 0.0,
        n_offers=record.n_offers or 0,
        sales_group=record.sales_group or None,
        material_group=record.material_group or None,
        score=score,
    )


class MatchOverrideRequest(BaseModel):
    pos_nr: int = Field(ge=1)
    artikel_nr: str = Field(min_length=1)


class ManualMatchRequest(BaseModel):
    artikel_nr: str = Field(min_length=1)


@router.post("/reviews/{review_id}/match-override")
def override_match(review_id: str, payload: MatchOverrideRequest) -> dict:
    return _set_manual_match(
        review_id=review_id,
        pos_nr=payload.pos_nr,
        artikel_nr=payload.artikel_nr,
    )


@router.put("/reviews/{review_id}/matches/{pos_nr}")
def set_manual_match(
    review_id: str,
    pos_nr: int,
    payload: ManualMatchRequest,
) -> dict:
    return _set_manual_match(
        review_id=review_id,
        pos_nr=pos_nr,
        artikel_nr=payload.artikel_nr,
    )


def _set_manual_match(review_id: str, pos_nr: int, artikel_nr: str) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    record = pipeline.stammdaten_repo.by_artikelnr(artikel_nr)
    if record is None:
        raise HTTPException(404, f"Stammdaten article '{artikel_nr}' not found")

    anfrage = _load_or_extract_anfrage(folder, review_id)

    if not any(p.pos_nr == pos_nr for p in anfrage.positionen):
        raise HTTPException(404, f"Position {pos_nr} not found in this review")

    matches = _load_or_recompute_matches(folder, anfrage, pipeline)

    new_match = MatchResult(
        pos_nr=pos_nr,
        status="exact",
        score=1.0,
        matched_artikelnr=record.artikel_nr,
        matched_bezeichnung=record.bezeichnung,
        matched_row=record.to_row(),
    )

    updated = _upsert_match(matches, new_match)
    write_json(folder / "matches_reviewed.json", [m.to_dict() for m in updated])
    _invalidate_approval(folder)

    return {
        "pos_nr": pos_nr,
        "matched_artikelnr": record.artikel_nr,
        "matched_bezeichnung": record.bezeichnung,
    }


# ============================================================================
# Helpers
# ============================================================================

def _build_mail(input_path: Path) -> Mail:
    if detect_file_type(input_path) in ("eml", "msg"):
        return parse_mail(input_path)

    return mail_from_file(input_path)


def _mail_from_meta(mail_meta: dict, folder: Path) -> Mail:
    """Reconstruct a Mail object from stored mail.json metadata."""
    attachments = []
    for att in mail_meta.get("attachments") or []:
        if isinstance(att, dict) and att.get("name"):
            path = folder / Path(att["name"]).name
            if path.exists():
                attachments.append(path)
    return Mail(
        subject=str(mail_meta.get("subject") or ""),
        sender=str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        body=str(mail_meta.get("body") or ""),
        attachments=attachments,
    )


def _try_load_anfrage_from_disk(folder: Path) -> Anfrage | None:
    """Return the first valid cached Anfrage from disk, or None if not found."""
    for path in (
        folder / "anfrage_reviewed.json",
        folder / "01_extracted.json",
        folder / "pipeline" / "01_extracted.json",
    ):
        data = read_json(path)
        if isinstance(data, dict) and data.get("positionen") is not None:
            return Anfrage.model_validate(data)
    return None


def _load_or_extract_anfrage(folder: Path, review_id: str) -> Anfrage:
    cached = _try_load_anfrage_from_disk(folder)
    if cached is not None:
        return cached

    pipeline = _get_pipeline()
    mail = _mail_from_meta(load_mail_meta(folder) or {}, folder)

    from quoting.pipeline import StepContext

    return pipeline.extract(mail, StepContext(work_dir=folder))


def _load_or_recompute_matches(
    folder: Path,
    anfrage: Anfrage,
    pipeline: QuotingPipeline,
) -> list[MatchResult]:
    data = read_json(folder / "matches_reviewed.json") or read_json(
        folder / "02_matches.json"
    )

    if isinstance(data, list):
        return [
            MatchResult(
                pos_nr=int(item.get("pos_nr", 0)),
                status=item.get("status", "no_match"),
                score=float(item.get("score", 0) or 0),
                matched_artikelnr=item.get("matched_artikelnr"),
                matched_bezeichnung=item.get("matched_bezeichnung"),
                matched_row=item.get("matched_row"),
            )
            for item in data
            if isinstance(item, dict)
        ]

    return match_positions(
        anfrage.positionen,
        pipeline.stammdaten,
        fuzzy_threshold=pipeline.settings.fuzzy_threshold,
        semantic_threshold=pipeline.settings.semantic_threshold,
    )


def _load_quotation(folder: Path):
    return load_saved_quotation(folder)


def _invalidate_approval(folder: Path) -> None:
    record = load_approval(folder)

    if record.state in {"approved", "ready_to_send"}:
        transition(folder, target="reviewed", actor=record.approved_by)


def _guess_media_type(path: Path) -> str:
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


def _file_response_inline(path: Path) -> FileResponse:
    return FileResponse(
        path,
        media_type=_guess_media_type(path),
        filename=path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )
