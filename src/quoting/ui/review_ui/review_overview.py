"""Hero block + KPI strip for the review-detail page.

Step rendering and navigation moved to :mod:`nav`.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.core import Anfrage


# --------------------------------------------------------------------- hero


def render_review_title(review_id: str | None, input_path: Path | None) -> None:
    """Render the hero block at the top of the review-detail page."""
    is_existing = bool(review_id)

    mode_chip = (
        '<span class="ek-chip ek-chip-success">'
        '<span class="ek-pill-dot"></span>'
        f"Bestehender Review · <code>{review_id}</code>"
        "</span>"
        if is_existing
        else '<span class="ek-chip ek-chip-brand">'
        '<span class="ek-pill-dot"></span>'
        "Neuer Upload"
        "</span>"
    )

    file_chip = (
        f'<span class="ek-chip">📄 {input_path.name}</span>'
        if input_path is not None and str(input_path) != "—"
        else ""
    )

    st.markdown(
        f"""
        <div class="ek-title-block">
            <h1 class="ek-title">
                Angebots-Review<span class="ek-accent-dot">.</span>
            </h1>
            <p class="ek-subtitle">
                KI-extrahierte Anfrage prüfen, Stammdaten-Treffer
                validieren und ein verkaufsfertiges Angebot erstellen.
            </p>
            <div class="ek-meta-row">
                {mode_chip}
                {file_chip}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------- KPIs


def render_review_overview(
    review_id: str | None,
    input_path: Path,
    anfrage: Anfrage,
    matches,
) -> None:
    """KPI strip for the current review."""
    total_positions = len(anfrage.positionen)
    exact = sum(1 for m in matches if m.status == "exact")
    fuzzy = sum(1 for m in matches if m.status == "fuzzy")
    semantic = sum(1 for m in matches if m.status == "semantic")
    no_match = sum(1 for m in matches if m.status == "no_match")
    matched = exact + fuzzy + semantic
    match_rate = matched / total_positions if total_positions else 0.0

    pdf_ready = bool(st.session_state.get("pdf_bytes"))
    quotation = st.session_state.get("quotation")
    total_eur = (
        f"{getattr(quotation, 'gesamtsumme', 0.0):,.2f} €"
        if quotation
        else "—"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Positionen", total_positions)
    c2.metric("Match-Quote", f"{match_rate:.0%}")
    c3.metric("Angebotssumme", total_eur)
    c4.metric("PDF", "Bereit" if pdf_ready else "Offen")
