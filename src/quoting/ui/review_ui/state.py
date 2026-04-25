from __future__ import annotations

import re
from pathlib import Path

import streamlit as st


EDITOR_KEY_PREFIXES = (
    "art_",
    "mng_",
    "eh_",
    "lt_",
    "ws_",
    "zn_",
    "bez_",
)


def reset_agent_state() -> None:
    for key in (
        "manual_discount_overrides",
        "agent_messages",
        "quotation",
        "quotation_hash",
        "pdf_bytes",
        "pdf_file_name",
        "generated_pdf_path",
    ):
        st.session_state.pop(key, None)


def reset_editor_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(EDITOR_KEY_PREFIXES):
            del st.session_state[key]


def safe_file_stub(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "angebot"