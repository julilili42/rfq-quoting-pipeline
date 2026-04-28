"""Resolve the input file for a given review-id and store context flags.

Exports :data:`REVIEWS_ROOT` so the dashboard can list all reviews on
disk, and :class:`ReviewInput` as the universal handle the rest of the
UI passes around.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import streamlit as st


# `src/quoting/ui/review_ui/review_context.py` -> 4 levels up = project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
REVIEWS_ROOT = PROJECT_ROOT / "data" / "reviews"

SUPPORTED_INPUT_SUFFIXES = {".pdf", ".msg", ".eml", ".xlsx", ".xls"}


@dataclass(frozen=True)
class ReviewInput:
    input_path: Path
    content_hash: str
    payload: bytes
    uploaded_name: str
    review_id: str | None = None
    review_dir: Path | None = None

    @property
    def work_dir(self) -> Path:
        """Where pipeline step artifacts live for this review.

        - Review mode: the review folder under ``data/reviews/``.
        - Upload mode: the upload temp folder (same dir the file lives in).

        Either way, the pipeline can write ``01_extracted.json``,
        ``02_matches.json``, ``03_quotation.json`` and the draft PDF here
        and they end up in a sensible place.
        """
        if self.review_dir is not None:
            return self.review_dir
        return self.input_path.parent


# ------------------------------------------------------------------ public

def get_review_id_from_query() -> str | None:
    for key in ("review_id", "id"):
        value = st.query_params.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value).strip()
    return None


def sanitize_review_id(raw_review_id: str) -> str:
    review_id = (raw_review_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", review_id):
        raise ValueError(f"Ungültige Review-ID: {raw_review_id!r}")
    return review_id


def load_review_input(raw_review_id: str) -> ReviewInput:
    review_id = sanitize_review_id(raw_review_id)
    review_dir = REVIEWS_ROOT / review_id
    if not review_dir.exists() or not review_dir.is_dir():
        raise FileNotFoundError(f"Review nicht gefunden: {review_dir}")
    meta = _load_review_meta(review_dir)
    input_path = _find_review_input_file(review_dir, meta)
    payload = input_path.read_bytes()
    return ReviewInput(
        input_path=input_path,
        content_hash=review_id,
        payload=payload,
        uploaded_name=input_path.name,
        review_id=review_id,
        review_dir=review_dir,
    )


def store_review_context(review_input: ReviewInput) -> None:
    if review_input.review_id and review_input.review_dir:
        st.session_state["review_id"] = review_input.review_id
        st.session_state["review_dir"] = str(review_input.review_dir)
        st.session_state["review_mode"] = "existing"
    else:
        st.session_state.pop("review_id", None)
        st.session_state.pop("review_dir", None)
        st.session_state["review_mode"] = "upload"


# ------------------------------------------------------------------ internal

def _load_review_meta(review_dir: Path) -> dict:
    meta_path = review_dir / "mail.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_review_input_file(review_dir: Path, meta: dict) -> Path:
    candidates = list(_candidate_paths_from_meta(review_dir, meta))
    candidates.extend(_candidate_paths_from_folder(review_dir))
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_valid_input_file(candidate):
            return candidate
    raise FileNotFoundError(
        f"Keine passende Eingabedatei in {review_dir} gefunden. "
        "Erwartet wird z. B. eine PDF-, MSG-, EML-, XLSX- oder XLS-Datei."
    )


def _candidate_paths_from_meta(review_dir: Path, meta: dict):
    direct_keys = (
        "input_path", "source_path", "file_path",
        "original_file", "filename", "name",
    )
    for key in direct_keys:
        value = meta.get(key)
        if isinstance(value, str):
            yield from _resolve_review_relative_path(review_dir, value)
    attachments = meta.get("attachments", [])
    if isinstance(attachments, list):
        for attachment in attachments:
            if isinstance(attachment, str):
                yield from _resolve_review_relative_path(review_dir, attachment)
            elif isinstance(attachment, dict):
                for key in ("path", "filename", "name"):
                    value = attachment.get(key)
                    if isinstance(value, str):
                        yield from _resolve_review_relative_path(
                            review_dir, value
                        )


def _resolve_review_relative_path(review_dir: Path, raw_path: str):
    path = Path(raw_path)
    if path.is_absolute():
        yield path
        return
    yield review_dir / path
    yield review_dir / "attachments" / path
    yield review_dir / "input" / path
    yield review_dir / "uploads" / path


def _candidate_paths_from_folder(review_dir: Path):
    preferred: list[Path] = []
    fallback: list[Path] = []
    for path in review_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            continue
        name = path.name.lower()
        if name.startswith("angebot") or "draft" in name or "quotation" in name:
            fallback.append(path)
        else:
            preferred.append(path)
    yield from preferred
    yield from fallback


def _is_valid_input_file(path: Path) -> bool:
    return (
        path.exists()
        and path.is_file()
        and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )
