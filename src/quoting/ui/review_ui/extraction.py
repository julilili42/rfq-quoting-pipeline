from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from quoting.core import Anfrage
from quoting.ui.review_agent import detect_agent_language
from quoting.ui.review_ui.resources import extract_cached, mail_body_cached
from quoting.ui.review_ui.state import reset_agent_state, reset_editor_state


def load_anfrage_once(
    content_hash: str,
    input_path: Path,
    work_dir: Path,
) -> Anfrage:
    if st.session_state.get("anfrage_hash") != content_hash:
        reset_editor_state()
        reset_agent_state()
        anfrage_dict = _load_saved_anfrage_dict()
        if anfrage_dict is None:
            anfrage_dict = extract_cached(
                content_hash, str(input_path), str(work_dir),
            )
            st.session_state["loaded_extraction_source"] = "neu extrahiert"
        st.session_state["anfrage"] = _coerce_current_anfrage(anfrage_dict)
        st.session_state["anfrage_hash"] = content_hash

    # Streamlit can keep old Pydantic model instances alive across hot reloads.
    # Re-validating through the current schema adds newly introduced defaults.
    st.session_state["anfrage"] = _coerce_current_anfrage(
        st.session_state["anfrage"],
    )
    return st.session_state["anfrage"]


def detect_and_store_agent_language(
    content_hash: str,
    input_path: Path,
    anfrage: Anfrage,
) -> str:
    mail_body_for_lang = mail_body_cached(str(input_path))
    fallback_lang_text = " ".join(
        [
            anfrage.kunde_firma or "",
            anfrage.kunde_ansprechpartner or "",
            anfrage.belegnummer or "",
            " ".join((p.source_quote or "") for p in anfrage.positionen[:3]),
        ]
    )
    if st.session_state.get("agent_lang_hash") != content_hash:
        st.session_state["agent_lang"] = detect_agent_language(
            mail_body_for_lang, fallback_lang_text,
        )
        st.session_state["agent_lang_hash"] = content_hash
    return st.session_state.get("agent_lang", "de")


def _load_saved_anfrage_dict() -> dict | None:
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        return None
    review_dir = Path(review_dir_raw)
    candidate_paths = [
        review_dir / "anfrage_reviewed.json",
        review_dir / "anfrage.json",
        review_dir / "extracted_anfrage.json",
        review_dir / "extraction.json",
        review_dir / "01_extracted.json",
        review_dir / "pipeline" / "01_extracted.json",
    ]
    candidate_paths.extend(sorted(review_dir.rglob("01_extracted.json")))
    seen: set[Path] = set()
    for path in candidate_paths:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            continue
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        normalized = _unwrap_anfrage_dict(data)
        if normalized is not None:
            try:
                st.session_state["loaded_extraction_source"] = str(
                    path.relative_to(review_dir)
                )
            except ValueError:
                st.session_state["loaded_extraction_source"] = str(path)
            return normalized
    return None


def _coerce_current_anfrage(value) -> Anfrage:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    return Anfrage.model_validate(value)


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _unwrap_anfrage_dict(data: dict) -> dict | None:
    if "positionen" in data and isinstance(data["positionen"], list):
        return data
    for key in ("anfrage", "request", "data"):
        nested = data.get(key)
        if isinstance(nested, dict) and "positionen" in nested:
            return nested
    return None
