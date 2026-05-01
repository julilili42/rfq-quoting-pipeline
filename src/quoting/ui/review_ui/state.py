"""Session-state helpers for the review UI.

Owns the small set of session-state keys that span multiple modules
(editor, quotation flow, agent chat, approval). Centralising them here
keeps reset/cleanup behaviour consistent.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

EDITOR_KEY_PREFIXES = (
    "ed_",
    "art_", "mng_", "eh_", "lt_", "ws_", "zn_", "bez_",
    "abm_", "gew_", "cert_", "zert_", "wsa_",
    "incoterms_", "zahl_",
    "price_",
)


def reset_agent_state() -> None:
    """Clear agent chat + generated quotation/PDF state."""
    for key in (
        "manual_discount_overrides",
        "agent_messages",
        "quotation",
        "quotation_hash",
        "pdf_bytes",
        "pdf_file_name",
        "generated_pdf_path",
        "editor_state_hash",
    ):
        st.session_state.pop(key, None)


def reset_editor_state() -> None:
    """Wipe editor widget keys + the change tracker."""
    for key in list(st.session_state.keys()):
        if key.startswith(EDITOR_KEY_PREFIXES):
            del st.session_state[key]
    st.session_state.pop("changed_fields", None)


def reset_review_state() -> None:
    """Full reset — used when the review-id changes or the user hits reset."""
    reset_agent_state()
    reset_editor_state()
    for key in (
        "anfrage",
        "anfrage_hash",
        "agent_lang",
        "agent_lang_hash",
        "loaded_extraction_source",
        "preview_view",
        "approval_actor",
    ):
        st.session_state.pop(key, None)


def safe_file_stub(name: str) -> str:
    """Filesystem-safe stem of an arbitrary filename."""
    stem = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "angebot"


def changed_fields_count() -> int:
    changed = st.session_state.get("changed_fields") or set()
    try:
        return len(changed)
    except Exception:
        return 0
