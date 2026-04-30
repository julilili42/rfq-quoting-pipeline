"""Hero block + KPI strip for the review-detail page.

Owns the small top-of-page render: a context breadcrumb that signals
where the user is in the larger Outlook → Pipeline → Review flow,
plus the page title and the single Review-ID chip. The sidebar no
longer carries a duplicate review-id box, so this is the canonical
place where the active review is identified.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.core import Anfrage


# --------------------------------------------------------------------- hero

def render_review_title(review_id: str | None, input_path: Path | None) -> None:
    """Render the breadcrumb + hero block at the top of the review page."""
    is_outlook_review = bool(review_id)

    _render_breadcrumb(is_outlook_review)

    review_chip = (
        '<span class="ek-chip ek-chip-success">'
        '<span class="ek-pill-dot"></span>'
        f"Review · <code>{review_id}</code>"
        "</span>"
        if is_outlook_review
        else '<span class="ek-chip ek-chip-brand">'
             '<span class="ek-pill-dot"></span>'
             "Direkter Upload"
             "</span>"
    )

    file_chip = (
        f'<span class="ek-chip ek-chip-muted">{input_path.name}</span>'
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
                {review_chip}
                {file_chip}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_breadcrumb(is_outlook_review: bool) -> None:
    """Slim trail showing the user's position in the larger workflow.

    For Outlook-originated reviews:
        Anfrage › Pipeline › **Review**

    For direct uploads (no Outlook context):
        Direkter Upload › **Review**

    The active node is the always "Review" — the user is inside the
    review UI. The breadcrumb is informational; nodes are not clickable
    because the upstream stages live outside this app.
    """
    if is_outlook_review:
        nodes = [
            ("Anfrage", False),
            ("Pipeline", False),
            ("Review", True),
        ]
    else:
        nodes = [
            ("Direkter Upload", False),
            ("Review", True),
        ]

    parts = ['<div class="ek-breadcrumb">']
    for i, (label, active) in enumerate(nodes):
        cls = "ek-breadcrumb-node active" if active else "ek-breadcrumb-node"
        parts.append(f'<span class="{cls}">{label}</span>')
        if i < len(nodes) - 1:
            parts.append('<span class="ek-breadcrumb-sep">›</span>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


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
