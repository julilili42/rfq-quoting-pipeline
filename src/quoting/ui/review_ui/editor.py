from __future__ import annotations

import streamlit as st

from quoting.core import Anfrage


def render_editor(anfrage: Anfrage) -> Anfrage:
    st.subheader("🤖 Extrahierte Daten")

    with st.expander("🏢 Header & Kundeninformationen", expanded=True):
        c_k1, c_k2 = st.columns(2)

        anfrage.kunde_firma = c_k1.text_input(
            "Firma",
            anfrage.kunde_firma or "",
        )
        anfrage.kunde_ansprechpartner = c_k2.text_input(
            "Ansprechpartner",
            anfrage.kunde_ansprechpartner or "",
        )
        anfrage.kunde_email = c_k1.text_input(
            "E-Mail",
            anfrage.kunde_email or "",
        )
        anfrage.belegnummer = c_k2.text_input(
            "Referenz-Nr",
            anfrage.belegnummer or "",
        )

    st.markdown("#### Positionen")

    icons = {
        "high": "🟢",
        "medium": "🟡",
        "low": "🔴",
    }

    edited_positions = []

    for i, pos in enumerate(anfrage.positionen):
        status_icon = icons.get(pos.confidence, "⚪")
        label = f"{status_icon} Pos {pos.pos_nr} — {pos.artikelnummer or 'Unbekannt'}"

        with st.expander(label):
            c1, c2 = st.columns(2)

            with c1:
                pos.artikelnummer = st.text_input(
                    "Art-Nr.",
                    pos.artikelnummer,
                    key=f"art_{i}",
                )
                pos.menge = st.number_input(
                    "Menge",
                    value=float(pos.menge),
                    key=f"mng_{i}",
                )
                pos.einheit = st.text_input(
                    "Einheit",
                    pos.einheit,
                    key=f"eh_{i}",
                )

            with c2:
                pos.liefertermin = st.text_input(
                    "Liefertermin",
                    pos.liefertermin or "",
                    key=f"lt_{i}",
                )
                pos.werkstoff = st.text_input(
                    "Werkstoff",
                    pos.werkstoff or "",
                    key=f"ws_{i}",
                )
                pos.zeichnungsnummer = st.text_input(
                    "Zeichnungs-Nr.",
                    pos.zeichnungsnummer or "",
                    key=f"zn_{i}",
                )

            pos.bezeichnung = st.text_area(
                "Bezeichnung",
                pos.bezeichnung,
                key=f"bez_{i}",
                height=70,
            )

            edited_positions.append(pos)

    anfrage.positionen = edited_positions
    st.session_state["anfrage"] = anfrage

    return anfrage