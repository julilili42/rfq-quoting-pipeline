from __future__ import annotations

import streamlit as st

from quoting.core import Anfrage
from quoting.matching import match_positions
from quoting.ui.review_ui.resources import settings, stammdaten


def render_matching(anfrage: Anfrage, fuzzy_threshold: int):
    st.markdown("---")
    st.subheader("🔗 Stammdaten-Abgleich")

    matches = match_positions(
        anfrage.positionen,
        stammdaten(),
        fuzzy_threshold=fuzzy_threshold,
        semantic_threshold=settings().semantic_threshold,
    )

    m_cols = st.columns(len(anfrage.positionen) if anfrage.positionen else 1)

    for i, (pos, match) in enumerate(zip(anfrage.positionen, matches)):
        with m_cols[i]:
            color = "normal" if match.score > 0.8 else "inverse"

            st.metric(
                f"Pos {pos.pos_nr}",
                f"{match.score:.0%}",
                match.status.upper(),
                delta_color=color,
            )

    return matches