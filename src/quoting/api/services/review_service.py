"""Review-level persistence and matching helpers.

Pure logic that operates on a review id + a ``QuotingPipeline``; no
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
from quoting.reviews import get_default_repository


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


def try_load_anfrage(review_id: str) -> Anfrage | None:
    """Return the first valid cached Anfrage, or None if not found."""
    data = get_default_repository().load_anfrage(review_id)
    if isinstance(data, dict) and data.get("positionen") is not None:
        return Anfrage.model_validate(data)
    return None


def try_load_original_anfrage(review_id: str) -> Anfrage | None:
    """Return the initial extraction snapshot, ignoring reviewed edits."""
    data = get_default_repository().load_extracted(review_id)
    if isinstance(data, dict) and data.get("positionen") is not None:
        return Anfrage.model_validate(data)
    return None


def build_mail(input_path: Path) -> Mail:
    if detect_file_type(input_path) in ("eml", "msg"):
        return parse_mail(input_path)
    return mail_from_file(input_path)


def mail_from_meta(mail_meta: dict, review_id: str) -> Mail:
    """Reconstruct a Mail object from stored input metadata."""
    repo = get_default_repository()
    attachments: list[Path] = []
    for att in mail_meta.get("attachments") or []:
        if not isinstance(att, dict) or not att.get("name"):
            continue
        doc = repo.current_document(review_id, kind="attachment", filename=str(att["name"]))
        path = _document_path(doc)
        if path is not None:
            attachments.append(path)
    return Mail(
        subject=str(mail_meta.get("subject") or ""),
        sender=str(mail_meta.get("from") or mail_meta.get("sender") or ""),
        body=str(mail_meta.get("body") or ""),
        attachments=attachments,
    )


def load_or_extract_anfrage(review_id: str, pipeline: QuotingPipeline) -> Anfrage:
    cached = try_load_anfrage(review_id)
    if cached is not None:
        return cached

    repo = get_default_repository()
    mail = mail_from_meta(repo.load_mail(review_id) or {}, review_id)

    from quoting.pipeline import StepContext

    folder = repo.artifact_dir(review_id)

    def snapshot_sink(name: str, data: Any) -> None:
        repo.save_payload(review_id, name, data)

    return pipeline.extract(mail, StepContext(work_dir=folder, snapshot_sink=snapshot_sink))


def load_or_recompute_matches(
    review_id: str,
    anfrage: Anfrage,
    pipeline: QuotingPipeline,
) -> list[MatchResult]:
    repo = get_default_repository()
    data = repo.load_matches(review_id)

    if isinstance(data, list) and data:
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


def invalidate_approval(review_id: str) -> None:
    record = load_approval(review_id)
    if record.state in {"approved", "ready_to_send"}:
        transition(review_id, target="reviewed", actor=record.approved_by)


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


def _document_path(doc: dict[str, Any] | None) -> Path | None:
    if not doc:
        return None
    path = Path(str(doc.get("storage_path") or ""))
    if path.exists() and path.is_file():
        return path
    return None
