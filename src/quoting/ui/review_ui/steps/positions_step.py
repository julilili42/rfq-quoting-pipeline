"""Step 1 — Positionen prüfen."""
from __future__ import annotations

import streamlit as st

from quoting.ui.review_ui.document_view import render_input_panel
from quoting.ui.review_ui.editor import render_positions_editor
from quoting.ui.review_ui.nav import render_step_nav
from quoting.ui.review_ui.quotation_flow import maybe_auto_refresh

def render_positions_step(review_input, anfrage, matches) -> None:
    """Render step 1: side-by-side positions editor + original document."""
    col_doc, col_review = st.columns([1, 1], gap="large")

    with col_review:
        render_positions_editor(anfrage, matches)

        maybe_auto_refresh(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )

    with col_doc:
        render_input_panel(review_input)

    st.markdown("---")
    render_step_nav(
        can_advance=True,
        forward_label="Positionen bestätigen",
    )
