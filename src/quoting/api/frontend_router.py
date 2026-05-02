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

import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quoting.api.approval_store import load_approval, transition
from quoting.api.progress_store import init_progress
from quoting.api.settings_store import load_user_settings
from quoting.core import Anfrage
from quoting.ingestion import Mail, detect_file_type, mail_from_file, parse_mail
from quoting.matching import MatchResult, match_positions
from quoting.output import build_draft_pdf
from quoting.pipeline import QuotingPipeline
from quoting.pricing import build_quotation
from quoting.reviews import (
    draft_pdf_filename,
    final_pdf_filename,
    find_draft_pdf,
    find_final_pdf,
    load_mail_meta,
    load_saved_quotation,
    read_json,
    scan_reviews,
    write_json,
)
from quoting.ui.review_agent import apply_manual_overrides


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = PROJECT_ROOT / "data" / "reviews"

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

    return {
        "review_id": review_id,
        "anfrage": anfrage.model_dump(mode="json"),
        "matches": [m.to_dict() for m in matches],
        "quotation": quotation.to_dict() if quotation else None,
        "manual_overrides": overrides,
        "mail": {
            "subject": str(mail_meta.get("subject") or ""),
            "from": str(mail_meta.get("from") or mail_meta.get("sender") or ""),
            "body": str(mail_meta.get("body") or ""),
            "attachments": list(mail_meta.get("attachments") or []),
        },
        "has_draft_pdf": find_draft_pdf(folder, review_id) is not None,
        "has_final_pdf": find_final_pdf(folder, review_id) is not None,
    }


@router.get("/reviews/{review_id}/mail")
def get_review_mail(review_id: str) -> dict:
    folder = _review_dir(review_id)
    meta = load_mail_meta(folder) or {}

    return {
        "subject": str(meta.get("subject") or ""),
        "from": str(meta.get("from") or meta.get("sender") or ""),
        "body": str(meta.get("body") or ""),
        "attachments": list(meta.get("attachments") or []),
    }


# ============================================================================
# Original input file
# ============================================================================

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

    return FileResponse(
        candidate,
        media_type=_guess_media_type(candidate),
        filename=candidate.name,
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


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


@router.post("/reviews/{review_id}/regenerate")
def regenerate_quotation(review_id: str) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    anfrage = _load_or_extract_anfrage(folder, review_id)
    matches = _load_or_recompute_matches(folder, anfrage, pipeline)
    overrides = read_json(folder / "manual_overrides.json") or []

    company_profile = load_user_settings().company
    quotation = build_quotation(anfrage, matches, pipeline.settings.preise_path)

    if isinstance(overrides, list) and overrides:
        quotation, _ = apply_manual_overrides(quotation, anfrage, overrides, lang="de")

    pdf_path = folder / draft_pdf_filename(review_id)

    build_draft_pdf(
        anfrage,
        quotation,
        pdf_path,
        is_final=False,
        company_profile=company_profile,
    )

    write_json(folder / "quotation_reviewed.json", quotation.to_dict())

    return quotation.to_dict()


class FinalizeRequest(BaseModel):
    actor: str = Field(min_length=1)


@router.post("/reviews/{review_id}/finalize")
def finalize_quotation(review_id: str, payload: FinalizeRequest) -> dict:
    folder = _review_dir(review_id)
    pipeline = _get_pipeline()

    anfrage = _load_or_extract_anfrage(folder, review_id)
    matches = _load_or_recompute_matches(folder, anfrage, pipeline)
    overrides = read_json(folder / "manual_overrides.json") or []

    company_profile = load_user_settings().company
    quotation = build_quotation(anfrage, matches, pipeline.settings.preise_path)

    if isinstance(overrides, list) and overrides:
        quotation, _ = apply_manual_overrides(quotation, anfrage, overrides, lang="de")

    final_path = folder / final_pdf_filename(review_id)

    build_draft_pdf(
        anfrage,
        quotation,
        final_path,
        is_final=True,
        company_profile=company_profile,
    )

    record = transition(
        folder,
        target="approved",
        actor=payload.actor,
        warning_acknowledged=True,
        final_pdf_path=final_path.name,
    )

    return {"final_pdf_path": record.final_pdf_path or final_path.name}


# ============================================================================
# Upload
# ============================================================================

@router.post("/reviews/upload")
async def upload_review(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(400, "Uploaded file is missing a filename")

    review_id = uuid.uuid4().hex[:12]
    folder = REVIEW_DIR / review_id
    folder.mkdir(parents=True, exist_ok=True)

    init_progress(folder, review_id)

    safe_name = Path(file.filename).name
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

    updated: list[MatchResult] = []
    replaced = False

    for match in matches:
        if match.pos_nr == pos_nr:
            updated.append(new_match)
            replaced = True
        else:
            updated.append(match)

    if not replaced:
        updated.append(new_match)

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


def _load_or_extract_anfrage(folder: Path, review_id: str) -> Anfrage:
    candidates = (
        folder / "anfrage_reviewed.json",
        folder / "01_extracted.json",
        folder / "pipeline" / "01_extracted.json",
    )

    for path in candidates:
        data = read_json(path)
        if isinstance(data, dict) and data.get("positionen") is not None:
            return Anfrage.model_validate(data)

    pipeline = _get_pipeline()
    mail_meta = load_mail_meta(folder) or {}

    attachments = []
    for att in mail_meta.get("attachments") or []:
        if isinstance(att, dict) and att.get("name"):
            path = folder / Path(att["name"]).name
            if path.exists():
                attachments.append(path)

    mail = Mail(
        subject=str(mail_meta.get("subject") or ""),
        sender=str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        body=str(mail_meta.get("body") or ""),
        attachments=attachments,
    )

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