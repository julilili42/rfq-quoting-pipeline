"""Streamlit editor for the extracted Anfrage.

Lets the reviewer correct customer details, commercial terms, and
per-position fields. The data is stored back into
``st.session_state["anfrage"]`` and returned so callers can keep using
a fresh reference.

Field changes are tracked in ``st.session_state["changed_fields"]`` for
the approval audit log.
"""
from __future__ import annotations

import streamlit as st

from quoting.core import Anfrage

_CONFIDENCE_META = {
    "high":   {"icon": "🟢", "label": "Hohe Sicherheit",    "tone": "success"},
    "medium": {"icon": "🟡", "label": "Mittlere Sicherheit", "tone": "warning"},
    "low":    {"icon": "🔴", "label": "Geringe Sicherheit",  "tone": "danger"},
}


def _track_change(field_path: str) -> None:
    changed = st.session_state.setdefault("changed_fields", set())
    changed.add(field_path)


def _input_with_tracking(
    *,
    kind: str,
    label: str,
    value,
    field_path: str,
    key: str,
    **kwargs,
):
    """Wrapper around streamlit inputs that records edits."""
    prev = value
    fn = {
        "text": st.text_input,
        "textarea": st.text_area,
        "number": st.number_input,
        "select": st.selectbox,
    }[kind]

    out = fn(label, value, key=key, **kwargs) if kind != "number" else fn(
        label, value=value, key=key, **kwargs
    )

    if out != prev:
        _track_change(field_path)
    return out


def _customer_block(anfrage: Anfrage) -> None:
    """Editable customer / header information — open by default."""
    with st.expander("👤 Kunde & Anfrage-Header", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            anfrage.kunde_firma = _input_with_tracking(
                kind="text", label="Firma",
                value=anfrage.kunde_firma or "",
                field_path="kunde_firma",
                key="ed_kunde_firma",
                placeholder="z. B. Musterfirma GmbH",
            )
            anfrage.kunde_email = _input_with_tracking(
                kind="text", label="E-Mail",
                value=anfrage.kunde_email or "",
                field_path="kunde_email",
                key="ed_kunde_email",
                placeholder="kontakt@firma.de",
            )
        with c2:
            anfrage.kunde_ansprechpartner = _input_with_tracking(
                kind="text", label="Ansprechpartner",
                value=anfrage.kunde_ansprechpartner or "",
                field_path="kunde_ansprechpartner",
                key="ed_kunde_ap",
                placeholder="z. B. Frau Müller",
            )
            anfrage.belegnummer = _input_with_tracking(
                kind="text", label="Anfrage / Beleg-Nr.",
                value=anfrage.belegnummer or "",
                field_path="belegnummer",
                key="ed_belegnummer",
                placeholder="z. B. ANF-2024-001",
            )

        c3, c4 = st.columns(2)
        with c3:
            anfrage.kundennummer = _input_with_tracking(
                kind="text", label="Kunden-Nr.",
                value=anfrage.kundennummer or "",
                field_path="kundennummer",
                key="ed_kundennr",
                placeholder="z. B. 1234",
            )
        with c4:
            anfrage.datum = _input_with_tracking(
                kind="text", label="Datum",
                value=anfrage.datum or "",
                field_path="datum",
                key="ed_datum",
                placeholder="z. B. 15.03.2024",
            )


def _commercial_block(anfrage: Anfrage) -> None:
    """Commercial terms — relevant for PDF generation. Collapsed by default."""
    with st.expander("💼 Kommerzielle Bedingungen", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            anfrage.incoterms = _input_with_tracking(
                kind="text", label="Lieferbedingung / Incoterms",
                value=anfrage.incoterms or "",
                field_path="incoterms",
                key="ed_incoterms",
                placeholder="z. B. EXW Werk",
                help="Wenn leer, werden die Werte aus den Einstellungen verwendet.",
            )
        with c2:
            anfrage.zahlungsbedingungen = _input_with_tracking(
                kind="text", label="Zahlungsbedingung",
                value=anfrage.zahlungsbedingungen or "",
                field_path="zahlungsbedingungen",
                key="ed_zahlungsbed",
                placeholder="z. B. 30 Tage netto",
                help="Wenn leer, werden die Werte aus den Einstellungen verwendet.",
            )


def _company_block() -> None:
    """Sender-side company data with quick-fill from settings."""
    from quoting.api.settings_store import load_settings

    settings = load_settings()
    profile = settings.company

    has_profile = bool(profile.company_name and profile.contact_person)

    with st.expander("🏢 Eigene Firmendaten (für das Angebots-PDF)", expanded=False):
        if has_profile:
            st.success(
                f"**{profile.company_name}** · {profile.contact_person} "
                f"({profile.contact_email or 'keine E-Mail'})",
                icon="✅",
            )
            st.caption(
                "Diese Daten werden automatisch in die Angebots-PDF übernommen. "
                "Ändern unter „Einstellungen“ in der Sidebar."
            )
        else:
            st.warning(
                "Keine Firmendaten hinterlegt. Bitte zuerst unter "
                "„Einstellungen“ in der Sidebar ausfüllen — sonst erscheinen "
                "Platzhalter im PDF.",
                icon="⚠️",
            )

        c1, c2, c3 = st.columns(3)
        c1.metric("Lieferbedingung", profile.delivery_term or "—")
        c2.metric("Zahlungsbedingung", profile.payment_term or "—")
        c3.metric("Gültigkeit", f"{profile.validity_days} Tage")


def _position_block(anfrage: Anfrage) -> list:
    """Editable per-position blocks. Returns the edited positions list."""
    st.markdown(
        '<div class="ek-section-label" style="margin-top:18px;">'
        f"📦 Positionen · {len(anfrage.positionen)}"
        "</div>",
        unsafe_allow_html=True,
    )

    edited_positions = []
    for i, pos in enumerate(anfrage.positionen):
        meta = _CONFIDENCE_META.get(
            pos.confidence,
            {"icon": "⚪", "label": "Unbekannt", "tone": ""},
        )
        label = (
            f"{meta['icon']}  Pos {pos.pos_nr} · "
            f"{pos.artikelnummer or 'Unbekannt'}  ·  "
            f"{int(pos.menge)} {pos.einheit}"
        )

        with st.expander(label, expanded=False):
            st.caption(f"KI-Sicherheit: **{meta['label']}**")
            c1, c2 = st.columns(2)
            with c1:
                pos.artikelnummer = _input_with_tracking(
                    kind="text", label="Artikelnummer",
                    value=pos.artikelnummer,
                    field_path=f"positionen[{i}].artikelnummer",
                    key=f"art_{i}",
                )
                pos.menge = _input_with_tracking(
                    kind="number", label="Menge",
                    value=float(pos.menge),
                    field_path=f"positionen[{i}].menge",
                    key=f"mng_{i}",
                )
                pos.einheit = _input_with_tracking(
                    kind="text", label="Einheit",
                    value=pos.einheit,
                    field_path=f"positionen[{i}].einheit",
                    key=f"eh_{i}",
                )
            with c2:
                pos.liefertermin = _input_with_tracking(
                    kind="text", label="Liefertermin",
                    value=pos.liefertermin or "",
                    field_path=f"positionen[{i}].liefertermin",
                    key=f"lt_{i}",
                )
                pos.werkstoff = _input_with_tracking(
                    kind="text", label="Werkstoff",
                    value=pos.werkstoff or "",
                    field_path=f"positionen[{i}].werkstoff",
                    key=f"ws_{i}",
                )
                pos.zeichnungsnummer = _input_with_tracking(
                    kind="text", label="Zeichnungs-Nr.",
                    value=pos.zeichnungsnummer or "",
                    field_path=f"positionen[{i}].zeichnungsnummer",
                    key=f"zn_{i}",
                )

            pos.bezeichnung = _input_with_tracking(
                kind="textarea", label="Bezeichnung",
                value=pos.bezeichnung,
                field_path=f"positionen[{i}].bezeichnung",
                key=f"bez_{i}",
                height=72,
            )

            c3, c4, c5 = st.columns(3)
            with c3:
                pos.abmessungen = _input_with_tracking(
                    kind="text", label="Abmessungen",
                    value=pos.abmessungen or "",
                    field_path=f"positionen[{i}].abmessungen",
                    key=f"abm_{i}",
                )
            with c4:
                pos.lieferzeit = _input_with_tracking(
                    kind="text", label="Lieferzeit",
                    value=pos.lieferzeit or "",
                    field_path=f"positionen[{i}].lieferzeit",
                    key=f"lz_{i}",
                    placeholder="z. B. 6 Wochen",
                )
            with c5:
                pos.lieferwerk = _input_with_tracking(
                    kind="text", label="Lieferwerk",
                    value=pos.lieferwerk or "",
                    field_path=f"positionen[{i}].lieferwerk",
                    key=f"lw_{i}",
                    placeholder="z. B. Werk Dettingen",
                )

            prev_cert = bool(pos.ist_zertifikat)
            pos.ist_zertifikat = st.checkbox(
                "Zertifikat / Pauschalposition",
                value=prev_cert,
                key=f"cert_{i}",
                help="Pauschal verrechnete Position (z. B. Abnahmeprüfzeugnis)",
            )
            if bool(pos.ist_zertifikat) != prev_cert:
                _track_change(f"positionen[{i}].ist_zertifikat")

            if pos.source_quote:
                st.caption(
                    f'**Quelle:** "{pos.source_quote[:120]}'
                    f'{"…" if len(pos.source_quote) > 120 else ""}"'
                )
        edited_positions.append(pos)
    return edited_positions


def _changes_indicator() -> None:
    """Show how many fields the user edited since extraction."""
    changed: set = st.session_state.get("changed_fields") or set()
    n = len(changed)
    if n == 0:
        return
    st.markdown(
        f"""
        <div class="ek-changes-indicator">
          <span class="ek-pill-dot"></span>
          <strong>{n}</strong> {'Änderung' if n == 1 else 'Änderungen'}
          gegenüber KI-Extraktion
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_editor(anfrage: Anfrage) -> Anfrage:
    """Render the full editor for an extracted Anfrage."""
    st.markdown(
        '<div class="ek-section-label">KI-extrahierte Daten · '
        "Bitte prüfen und korrigieren</div>",
        unsafe_allow_html=True,
    )

    _changes_indicator()
    _customer_block(anfrage)
    _commercial_block(anfrage)
    _company_block()
    anfrage.positionen = _position_block(anfrage)

    st.session_state["anfrage"] = anfrage
    return anfrage
