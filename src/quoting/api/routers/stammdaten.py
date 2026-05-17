"""Stammdaten search, manual matching, and custom-article creation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from quoting.api import _common
from quoting.api.services import review_service as rs
from quoting.api.services.quotation_service import remove_position_price_overrides
from quoting.matching import MatchResult
from quoting.reviews import ReviewFiles, read_json_list, write_json

router = APIRouter()


# --------------------------------------------------------------------------- search
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


@router.get("/stammdaten/search", response_model=list[StammdatenHit])
def search_stammdaten(
    q: str = Query("", description="Free-text query"),
    limit: int = Query(25, ge=1, le=100),
) -> list[StammdatenHit]:
    from rapidfuzz import fuzz, process

    query = (q or "").strip()
    pipeline = _common.get_pipeline()
    records = pipeline.stammdaten_repo.all()

    if not query:
        return [
            _record_to_hit(record, score=1.0)
            for record in sorted(records, key=lambda r: r.artikel_nr)[:limit]
        ]

    if not records:
        return []

    # Exact artikel_nr match — return immediately without fuzzy scoring
    normalised_query = rs.normalise_article_key(query)
    exact = next(
        (r for r in records if rs.normalise_article_key(r.artikel_nr) == normalised_query),
        None,
    )
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


# --------------------------------------------------------------------------- manual matching
class MatchOverrideRequest(BaseModel):
    pos_nr: int = Field(ge=1)
    artikel_nr: str = Field(min_length=1)


class ManualMatchRequest(BaseModel):
    artikel_nr: str = Field(min_length=1)


class CustomArticleRequest(BaseModel):
    pos_nr: int = Field(ge=1)
    artikel_nr: str = Field(min_length=1, max_length=80)
    bezeichnung: str = Field(min_length=1, max_length=500)
    einheit: str = Field(default="Stk", min_length=1, max_length=20)
    unit_price_eur: float = Field(gt=0)
    werkstoff: str | None = Field(default=None, max_length=200)
    abmessungen: str | None = Field(default=None, max_length=200)


def _set_manual_match(review_id: str, pos_nr: int, artikel_nr: str) -> dict:
    folder = _common.review_dir(review_id)
    pipeline = _common.get_pipeline()

    record = pipeline.stammdaten_repo.by_artikelnr(artikel_nr)
    if record is None:
        raise HTTPException(404, f"Stammdaten article '{artikel_nr}' not found")

    anfrage = rs.load_or_extract_anfrage(folder, pipeline)

    if not any(p.pos_nr == pos_nr for p in anfrage.positionen):
        raise HTTPException(404, f"Position {pos_nr} not found in this review")

    matches = rs.load_or_recompute_matches(folder, anfrage, pipeline)

    new_match = MatchResult(
        pos_nr=pos_nr,
        status="exact",
        score=1.0,
        matched_artikelnr=record.artikel_nr,
        matched_bezeichnung=record.bezeichnung,
        matched_row=record.to_row(),
    )

    updated = rs.upsert_match(matches, new_match)
    write_json(folder / ReviewFiles.MATCHES_REVIEWED, [m.to_dict() for m in updated])
    rs.invalidate_approval(folder)

    return {
        "pos_nr": pos_nr,
        "matched_artikelnr": record.artikel_nr,
        "matched_bezeichnung": record.bezeichnung,
    }


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


@router.post("/reviews/{review_id}/custom-article")
def create_custom_article_match(
    review_id: str,
    payload: CustomArticleRequest,
) -> dict:
    folder = _common.review_dir(review_id)
    pipeline = _common.get_pipeline()

    artikel_nr = rs.clean_required_text(payload.artikel_nr, "artikel_nr")
    bezeichnung = rs.clean_required_text(payload.bezeichnung, "bezeichnung")
    einheit = rs.clean_required_text(payload.einheit, "einheit")
    werkstoff = rs.clean_optional_text(payload.werkstoff)
    abmessungen = rs.clean_optional_text(payload.abmessungen)
    unit_price = round(float(payload.unit_price_eur), 2)

    if rs.find_stammdaten_by_article(pipeline, artikel_nr) is not None:
        raise HTTPException(
            409,
            f"Stammdaten article '{artikel_nr}' already exists",
        )

    anfrage = rs.load_or_extract_anfrage(folder, pipeline)
    positions = []
    position_found = False

    for pos in anfrage.positionen:
        if pos.pos_nr != payload.pos_nr:
            positions.append(pos)
            continue

        positions.append(
            pos.model_copy(
                update={
                    "artikelnummer": artikel_nr,
                    "bezeichnung": bezeichnung,
                    "einheit": einheit,
                    "werkstoff": werkstoff,
                    "abmessungen": abmessungen,
                    "confidence": "high",
                }
            )
        )
        position_found = True

    if not position_found:
        raise HTTPException(404, f"Position {payload.pos_nr} not found in this review")

    updated_anfrage = anfrage.model_copy(update={"positionen": positions})
    write_json(folder / ReviewFiles.ANFRAGE_REVIEWED, updated_anfrage.model_dump(mode="json"))

    custom_row = {
        "artikel_nr": artikel_nr,
        "bezeichnung": bezeichnung,
        "werkstoff": werkstoff,
        "abmessungen": abmessungen,
        "einheit": einheit,
        "basispreis_eur": unit_price,
        "zkalk_offset_eur": 0.0,
        "preis_min_eur": unit_price,
        "preis_max_eur": unit_price,
        "sales_group": "Custom",
        "material_group": "Custom",
        "n_offers": 0,
        "source": "custom",
        "custom": True,
    }

    matches = rs.load_or_recompute_matches(folder, updated_anfrage, pipeline)
    new_match = MatchResult(
        pos_nr=payload.pos_nr,
        status="exact",
        score=1.0,
        matched_artikelnr=artikel_nr,
        matched_bezeichnung=bezeichnung,
        matched_row=custom_row,
    )
    updated_matches = rs.upsert_match(matches, new_match)
    write_json(folder / ReviewFiles.MATCHES_REVIEWED, [m.to_dict() for m in updated_matches])

    overrides = read_json_list(folder / ReviewFiles.MANUAL_OVERRIDES)
    write_json(
        folder / ReviewFiles.MANUAL_OVERRIDES,
        remove_position_price_overrides(overrides, payload.pos_nr),
    )

    rs.invalidate_approval(folder)

    return {
        "pos_nr": payload.pos_nr,
        "matched_artikelnr": artikel_nr,
        "matched_bezeichnung": bezeichnung,
        "unit_price_eur": unit_price,
    }
