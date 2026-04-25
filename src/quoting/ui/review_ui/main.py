from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


def _ensure_project_path() -> None:
    """Allow running this file directly via streamlit."""
    this_file = Path(__file__).resolve()

    # src/quoting/ui/review_ui/main.py
    project_root = this_file.parents[4]
    src_dir = this_file.parents[3]

    for p in (project_root, src_dir):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _configure_page() -> None:
    st.set_page_config(
        page_title="ElringKlinger | Quotation Review",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def run() -> None:
    _ensure_project_path()
    _configure_page()

    from quoting.ui.review_ui.agent_chat import render_agent_chat
    from quoting.ui.review_ui.document_view import render_original_request
    from quoting.ui.review_ui.editor import render_editor
    from quoting.ui.review_ui.extraction import detect_and_store_agent_language, load_anfrage_once
    from quoting.ui.review_ui.layout import apply_style, render_header, render_sidebar
    from quoting.ui.review_ui.matching_view import render_matching
    from quoting.ui.review_ui.quotation_flow import render_generate_button
    from quoting.ui.review_ui.upload import handle_upload

    apply_style()
    render_header()

    uploaded, fuzzy_threshold = render_sidebar()

    st.markdown('<h1 class="main-header">📋 Angebots-Review</h1>', unsafe_allow_html=True)

    if not uploaded:
        st.info("Bitte laden Sie links eine Preisanfrage hoch, um zu beginnen.")
        st.stop()

    input_path, content_hash, payload = handle_upload(uploaded)

    try:
        anfrage = load_anfrage_once(content_hash, input_path)
    except Exception as e:
        st.error(f"❌ Fehler bei der Extraktion: {e}")
        st.stop()

    detect_and_store_agent_language(content_hash, input_path, anfrage)

    col_doc, col_extract = st.columns([1, 1], gap="large")

    with col_doc:
        render_original_request(input_path, payload)

    with col_extract:
        anfrage = render_editor(anfrage)

    matches = render_matching(anfrage, fuzzy_threshold)

    render_generate_button(
        anfrage=anfrage,
        matches=matches,
        content_hash=content_hash,
        uploaded_name=uploaded.name,
    )

    render_agent_chat(
        anfrage=anfrage,
        matches=matches,
        content_hash=content_hash,
    )


if __name__ == "__main__":
    run()