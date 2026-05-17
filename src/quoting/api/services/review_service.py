"""Review-level persistence and matching helpers.

Pure logic that operates on a review folder + a ``QuotingPipeline``; no
FastAPI dependencies. Used by the reviews/stammdaten routers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quoting.api.approval_store import load_approval, transition
from quoting.core import Anfrage
from quoting.ingestion import Mail, detect_file_type, mail_from_file, parse_mail
from quoting.matching import MatchResult, match_positions
from quoting.pipeline import QuotingPipeline
from quoting.reviews import (
    ReviewFiles,
    load_mail_meta,
    read_json,
)


def normalise_article_key(value: str | None) -> str:
    return "".join((value or "").upper().split())


def find_stammdaten_by_article(pipeline: QuotingPipeline, artikelnummer: str) -> Any | None:
    needle = normalise_article_key(artikelnummer)
    if not needle:
        return None
    for record in pipeline.stammdaten_repo.all():
        if normalise_article_key(record.artikel_nr) == needle:
            return record
    return None


def try_load_anfrage_from_disk(folder: Path) -> Anfrage | None:
    """Return the first valid cached Anfrage from disk, or None if not found."""
    for path in (
        folder / ReviewFiles.ANFRAGE_REVIEWED,
        folder / ReviewFiles.EXTRACTED,
        folder / "pipeline" / "01_extracted.json",
    ):
        data = read_json(path)
        if isinstance(data, dict) and data.get("positionen") is not None:
            return Anfrage.model_validate(data)
    return None


def try_load_original_anfrage_from_disk(folder: Path) -> Anfrage | None:
    """Return the initial extraction snapshot, ignoring reviewed edits."""
    for path in (
        folder / ReviewFiles.EXTRACTED,
        folder / "pipeline" / "01_extracted.json",
    ):
        data = read_json(path)
        if isinstance(data, dict) and data.get("positionen") is not None:
            return Anfrage.model_validate(data)
    return None


def build_mail(input_path: Path) -> Mail:
    if detect_file_type(input_path) in ("eml", "msg"):
        return parse_mail(input_path)
    return mail_from_file(input_path)


def mail_from_meta(mail_meta: dict, folder: Path) -> Mail:
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


def load_or_extract_anfrage(folder: Path, pipeline: QuotingPipeline) -> Anfrage:
    cached = try_load_anfrage_from_disk(folder)
    if cached is not None:
        return cached

    mail = mail_from_meta(load_mail_meta(folder) or {}, folder)

    from quoting.pipeline import StepContext

    return pipeline.extract(mail, StepContext(work_dir=folder))


def load_or_recompute_matches(
    folder: Path,
    anfrage: Anfrage,
    pipeline: QuotingPipeline,
) -> list[MatchResult]:
    data = read_json(folder / ReviewFiles.MATCHES_REVIEWED) or read_json(
        folder / "02_matches.json"
    )

    if isinstance(data, list):
        saved_matches = [
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
        active_pos_nrs = {pos.pos_nr for pos in anfrage.positionen}
        saved_by_pos = {
            match.pos_nr: match
            for match in saved_matches
            if match.pos_nr in active_pos_nrs
        }

        if len(saved_by_pos) == len(active_pos_nrs):
            return [saved_by_pos[pos.pos_nr] for pos in anfrage.positionen]

        recomputed = match_positions(
            anfrage.positionen,
            pipeline.stammdaten,
            fuzzy_threshold=pipeline.settings.fuzzy_threshold,
            semantic_threshold=pipeline.settings.semantic_threshold,
        )
        return [saved_by_pos.get(match.pos_nr, match) for match in recomputed]

    return match_positions(
        anfrage.positionen,
        pipeline.stammdaten,
        fuzzy_threshold=pipeline.settings.fuzzy_threshold,
        semantic_threshold=pipeline.settings.semantic_threshold,
    )


def enrich_exact_article_edits(
    anfrage: Anfrage,
    previous: Anfrage | None,
    pipeline: QuotingPipeline,
) -> Anfrage:
    """Fill Stammdaten fields when a user changed a position to an exact article.

    This mirrors the manual "Artikel zuordnen" behaviour, but only for
    article-number edits. Existing descriptions are left alone when the
    article number did not change so a deliberate text edit is not reverted on
    the next save.
    """
    previous_by_pos = {p.pos_nr: p for p in previous.positionen} if previous else {}
    next_positions = []
    changed = False

    for pos in anfrage.positionen:
        previous_pos = previous_by_pos.get(pos.pos_nr)
        article_changed = (
            previous_pos is None
            or normalise_article_key(previous_pos.artikelnummer)
            != normalise_article_key(pos.artikelnummer)
        )
        if not article_changed or not pos.artikelnummer.strip():
            next_positions.append(pos)
            continue

        record = find_stammdaten_by_article(pipeline, pos.artikelnummer)
        if record is None:
            next_positions.append(pos)
            continue

        enriched = pos.model_copy(
            update={
                "artikelnummer": record.artikel_nr,
                "bezeichnung": record.bezeichnung or pos.bezeichnung,
                "werkstoff": record.werkstoff if record.werkstoff is not None else pos.werkstoff,
                "abmessungen": record.abmessungen if record.abmessungen is not None else pos.abmessungen,
                "einheit": record.einheit or pos.einheit,
            }
        )
        next_positions.append(enriched)
        changed = changed or enriched != pos

    if not changed:
        return anfrage
    return anfrage.model_copy(update={"positionen": next_positions})


def upsert_match(matches: list[MatchResult], new_match: MatchResult) -> list[MatchResult]:
    """Replace an existing match by pos_nr, or append if not found."""
    updated = [new_match if m.pos_nr == new_match.pos_nr else m for m in matches]
    if not any(m.pos_nr == new_match.pos_nr for m in matches):
        updated.append(new_match)
    return updated


def invalidate_approval(folder: Path) -> None:
    record = load_approval(folder)
    if record.state in {"approved", "ready_to_send"}:
        transition(folder, target="reviewed", actor=record.approved_by)


def clean_required_text(value: str, field_name: str) -> str:
    from fastapi import HTTPException

    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise HTTPException(400, f"{field_name} must not be empty")
    return cleaned


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None
