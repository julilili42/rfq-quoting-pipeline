from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.core import Anfrage
from quoting.ui.review_agent import detect_agent_language
from quoting.ui.review_ui.resources import extract_cached, mail_body_cached
from quoting.ui.review_ui.state import reset_agent_state, reset_editor_state


def load_anfrage_once(content_hash: str, input_path: Path) -> Anfrage:
    if st.session_state.get("anfrage_hash") != content_hash:
        reset_editor_state()
        reset_agent_state()

        anfrage_dict = extract_cached(content_hash, str(input_path))

        st.session_state["anfrage"] = Anfrage.model_validate(anfrage_dict)
        st.session_state["anfrage_hash"] = content_hash

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
            mail_body_for_lang,
            fallback_lang_text,
        )
        st.session_state["agent_lang_hash"] = content_hash

    return st.session_state.get("agent_lang", "de")