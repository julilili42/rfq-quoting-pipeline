"""Streamlit editor for the extracted Anfrage.

Two human-task entry points that mirror the new review workflow:

- :func:`render_positions_editor` — Step 1 (positions + matching).
  Each position carries a *compact* inline match chip showing how the AI
  matched it against the master data. Positions stay collapsed until the
  reviewer opens them.

- :func:`render_customer_editor` — Step 2 (customer header + commercial
  terms + sender company profile). Defaults are pulled from the user's
  settings and can be overridden per offer; the override propagates
  back into the Anfrage so subsequent PDF renders pick it up.

Field changes are tracked in ``st.session_state["changed_fields"]`` for
the approval audit log.
"""
from __future__ import annotations

from html import escape

import streamlit as st

from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.ui.review_agent import upsert_override



_CONFIDENCE_LABEL = {
    "high":   "hoch",
    "medium": "mittel",
    "low":    "gering",
}

_MATCH_LABEL = {
    "exact":    "Exakt",
    "fuzzy":    "Fuzzy",
    "semantic": "Semantisch",
    "no_match": "Kein Treffer",
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


# --------------------------------------------------------------------- public

def render_positions_editor(
    anfrage: Anfrage,
    matches: list[MatchResult],
) -> Anfrage:
    """Step 1: positions + per-position matching info."""
    st.markdown(
        '<div class="ek-section-label">Positionen prüfen</div>',
        unsafe_allow_html=True,
    )

    _changes_indicator()
    _matching_summary(matches)

    anfrage.positionen = _position_block(anfrage, matches=matches)
    st.session_state["anfrage"] = anfrage
    return anfrage


def render_customer_editor(anfrage: Anfrage) -> Anfrage:
    """Step 2: customer + commercial terms + sender company data."""
    st.markdown(
        '<div class="ek-section-label">Kundendaten prüfen</div>',
        unsafe_allow_html=True,
    )

    _changes_indicator()
    _customer_validation(anfrage)
    _customer_block(anfrage)
    _commercial_block(anfrage)
    _company_block()

    st.session_state["anfrage"] = anfrage
    return anfrage


def render_editor(anfrage: Anfrage) -> Anfrage:
    """Legacy combined editor (back-compat alias)."""
    st.markdown(
        '<div class="ek-section-label">'
        "KI-extrahierte Daten · Bitte prüfen und korrigieren"
        "</div>",
        unsafe_allow_html=True,
    )

    _changes_indicator()
    _customer_block(anfrage)
    _commercial_block(anfrage)
    _company_block()
    anfrage.positionen = _position_block(anfrage)

    st.session_state["anfrage"] = anfrage
    return anfrage


# --------------------------------------------------------------------- blocks

def _customer_block(anfrage: Anfrage) -> None:
    """Editable customer / header information — open by default."""
    with st.expander("Kunde & Anfrage-Header", expanded=True):
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
    """Commercial terms — pulls defaults from settings, allows override.

    The defaults shown here come from the user's company profile; any
    edit replaces the default for *this* Anfrage and is what the PDF
    renderer will use. Empty values fall back to the profile.
    """
    from quoting.api.settings_store import load_settings

    profile = load_settings().company

    with st.expander("Kommerzielle Bedingungen", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            current_incoterms = (anfrage.incoterms or "").strip()
            display_incoterms = current_incoterms or (profile.delivery_term or "")
            new_incoterms = _input_with_tracking(
                kind="text", label="Lieferbedingung / Incoterms",
                value=display_incoterms,
                field_path="incoterms",
                key="ed_incoterms",
                placeholder="z. B. EXW Werk",
                help=(
                    f"Standard aus den Einstellungen: "
                    f"{profile.delivery_term or '—'}"
                ),
            )
            # Only persist into the Anfrage if the user actually typed
            # something — keep the field "empty" when it matches the
            # default so settings changes propagate naturally.
            if new_incoterms.strip() != (profile.delivery_term or "").strip():
                anfrage.incoterms = new_incoterms or None
            else:
                anfrage.incoterms = None

        with c2:
            current_pay = (anfrage.zahlungsbedingungen or "").strip()
            display_pay = current_pay or (profile.payment_term or "")
            new_pay = _input_with_tracking(
                kind="text", label="Zahlungsbedingung",
                value=display_pay,
                field_path="zahlungsbedingungen",
                key="ed_zahlungsbed",
                placeholder="z. B. 30 Tage netto",
                help=(
                    f"Standard aus den Einstellungen: "
                    f"{profile.payment_term or '—'}"
                ),
            )
            if new_pay.strip() != (profile.payment_term or "").strip():
                anfrage.zahlungsbedingungen = new_pay or None
            else:
                anfrage.zahlungsbedingungen = None


def _company_block() -> None:
    """Sender-side company data — quick-fill from settings, override per offer.

    Edits here are stored on the session for *this* review only and
    the PDF renderer picks them up via :func:`get_effective_company_profile`.
    They do not persist back to the global settings.
    """
    from dataclasses import replace

    from quoting.api.settings_store import load_settings

    base_profile = load_settings().company
    has_profile = bool(base_profile.company_name and base_profile.contact_person)

    overrides: dict = st.session_state.get("company_profile_overrides", {})

    def _val(field: str) -> str:
        if field in overrides:
            return str(overrides[field] or "")
        return str(getattr(base_profile, field, "") or "")

    with st.expander(
        "Eigene Firmendaten (für das Angebots-PDF)",
        expanded=False,
    ):
        if has_profile and not overrides:
            st.caption(
                f"Standardwerte aus den Einstellungen werden verwendet. "
                f"Hier kannst du sie für *dieses* Angebot überschreiben."
            )
        elif overrides:
            st.caption(
                "Es sind individuelle Anpassungen für dieses Angebot aktiv."
            )
        else:
            st.warning(
                "Keine Firmendaten in den Einstellungen. Bitte zuerst "
                "unter „Einstellungen“ ausfüllen — sonst erscheinen "
                "Platzhalter im PDF.",
            )

        new_overrides: dict = {}

        c1, c2 = st.columns(2)
        with c1:
            new_overrides["company_name"] = st.text_input(
                "Firmenname",
                value=_val("company_name"),
                key="company_override_name",
                placeholder="z. B. ElringKlinger Kunststofftechnik GmbH",
            )
            new_overrides["contact_person"] = st.text_input(
                "Kontaktperson",
                value=_val("contact_person"),
                key="company_override_contact",
                placeholder="z. B. Max Mustermann",
            )
            new_overrides["contact_phone"] = st.text_input(
                "Telefon",
                value=_val("contact_phone"),
                key="company_override_phone",
                placeholder="+49 …",
            )
        with c2:
            new_overrides["contact_email"] = st.text_input(
                "E-Mail",
                value=_val("contact_email"),
                key="company_override_email",
                placeholder="vertrieb@firma.de",
            )
            new_overrides["delivery_term"] = st.text_input(
                "Standard-Lieferbedingung",
                value=_val("delivery_term"),
                key="company_override_delivery",
                placeholder="z. B. EXW Werk",
                help="Wirkt nur, wenn die Anfrage selbst keine "
                     "Lieferbedingung enthält.",
            )
            new_overrides["payment_term"] = st.text_input(
                "Standard-Zahlungsbedingung",
                value=_val("payment_term"),
                key="company_override_payment",
                placeholder="z. B. 30 Tage netto",
            )

        # Track an override only if it differs from the saved profile.
        diff: dict = {}
        for key, val in new_overrides.items():
            if str(val or "") != str(getattr(base_profile, key, "") or ""):
                diff[key] = val
        if diff != overrides:
            _track_change("company_profile")
            st.session_state["company_profile_overrides"] = diff


def get_effective_company_profile():
    """Resolve the company profile to use for *this* PDF render.

    Combines the saved settings profile with any per-review overrides
    that the user typed into the editor.
    """
    from dataclasses import replace
    from quoting.api.settings_store import load_settings

    base = load_settings().company
    overrides = st.session_state.get("company_profile_overrides") or {}
    if not overrides:
        return base
    return replace(base, **overrides)


def _position_block(
    anfrage: Anfrage,
    matches: list[MatchResult] | None = None,
) -> list:
    """Editable per-position blocks. Returns the edited positions list."""
    matches_by_pos: dict[int, MatchResult] = {
        m.pos_nr: m for m in (matches or [])
    }

    if not matches:
        st.markdown(
            '<div class="ek-section-label" style="margin-top:18px;">'
            f"Positionen · {len(anfrage.positionen)}"
            "</div>",
            unsafe_allow_html=True,
        )

    edited_positions = []
    for i, pos in enumerate(anfrage.positionen):
        match = matches_by_pos.get(pos.pos_nr)
        label = (
            f"Pos {pos.pos_nr} · "
            f"{pos.artikelnummer or 'Unbekannt'} · "
            f"{int(pos.menge)} {pos.einheit}"
        )

        with st.expander(label, expanded=False):
            if match is not None:
                _render_match_chip(match)

            st.caption(
                f"KI-Sicherheit: {_CONFIDENCE_LABEL.get(pos.confidence, pos.confidence)}"
            )

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

                _render_position_price_field(pos, i)
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
                    f'**Quelle aus der Anfrage:** "{pos.source_quote[:160]}'
                    f'{"…" if len(pos.source_quote) > 160 else ""}"'
                )

        edited_positions.append(pos)

    return edited_positions


# ------------------------------------------------------------------ helpers

def _render_match_chip(match: MatchResult) -> None:
    """Compact, single-line match-status chip at the top of a position.

    Replaces the previous full-width Streamlit callouts which were too
    visually loud. The chip shows status + score + matched article in
    one line, color-coded via CSS.
    """
    status = match.status
    label = _MATCH_LABEL.get(status, status)
    score_pct = f"{match.score:.0%}" if match.score else None

    if status == "no_match":
        meta_html = "kein Stammdaten-Treffer"
    else:
        article = escape(match.matched_artikelnr or "—")
        bezeichnung = escape((match.matched_bezeichnung or "")[:80])
        bits = [f"<code>{article}</code>"]
        if score_pct:
            bits.append(f"Score {score_pct}")
        if bezeichnung:
            bits.append(bezeichnung)
        meta_html = " · ".join(bits)

    st.markdown(
        f'<div class="ek-match-chip {status}">'
        f'<span class="ek-pill-dot"></span>'
        f'<span class="ek-match-chip-label">{label}</span>'
        f'<span class="ek-match-chip-meta">{meta_html}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _matching_summary(matches: list[MatchResult]) -> None:
    """Subtle inline summary of the match-status distribution."""
    if not matches:
        return
    exact = sum(1 for m in matches if m.status == "exact")
    fuzzy = sum(1 for m in matches if m.status == "fuzzy")
    semantic = sum(1 for m in matches if m.status == "semantic")
    no_match = sum(1 for m in matches if m.status == "no_match")

    items = (
        ("exact", "Exakt", exact),
        ("fuzzy", "Fuzzy", fuzzy),
        ("semantic", "Semantisch", semantic),
        ("no_match", "Kein Treffer", no_match),
    )
    summary = "".join(
        f'<span class="ek-match-summary-item {status}">'
        f'<span class="ek-match-summary-count">{count}</span>'
        f'<span>{label}</span>'
        f'</span>'
        for status, label, count in items
    )
    st.markdown(
        f'<div class="ek-match-summary">{summary}</div>',
        unsafe_allow_html=True,
    )


def _customer_validation(anfrage: Anfrage) -> None:
    """Lightweight validation: surface obviously missing fields."""
    missing: list[str] = []
    if not (anfrage.kunde_firma or "").strip():
        missing.append("Firma")
    if (
        not (anfrage.kunde_email or "").strip()
        and not (anfrage.kunde_ansprechpartner or "").strip()
    ):
        missing.append("Ansprechpartner oder E-Mail")

    if missing:
        st.warning(
            f"Fehlende oder leere Pflichtfelder: **{', '.join(missing)}**. "
            "Bitte vor Bestätigung ergänzen.",
        )


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


def _render_position_price_field(pos, index: int) -> None:
    """Inline price override inside the existing position expander."""
    quotation = st.session_state.get("quotation")
    if not quotation:
        st.caption("Preis wird angezeigt, sobald ein Angebotsentwurf berechnet wurde.")
        return

    item = _quotation_item_for_pos(quotation, pos.pos_nr)
    if item is None:
        st.caption("Noch kein Preis für diese Position vorhanden.")
        return

    current_price = _current_manual_unit_price(
        pos_nr=pos.pos_nr,
        fallback=float(item.einzelpreis),
    )

    new_price = st.number_input(
        "Stückpreis EUR",
        min_value=0.0,
        value=float(current_price),
        step=0.01,
        format="%.2f",
        key=f"price_unit_{index}",
        help="Überschreibt den berechneten Stückpreis für diese Position.",
    )

    if abs(float(new_price) - float(current_price)) < 0.005:
        return

    overrides = list(st.session_state.get("manual_discount_overrides") or [])
    st.session_state["manual_discount_overrides"] = upsert_override(
        overrides,
        {
            "target": "pos",
            "pos_nr": int(pos.pos_nr),
            "mode": "unit_price_eur",
            "unit_price_eur": round(float(new_price), 2),
        },
    )

    _track_change(f"positionen[{index}].einzelpreis")
    st.session_state.pop("editor_state_hash", None)
    _invalidate_approval_after_price_change()
    st.rerun()


def _quotation_item_for_pos(quotation, pos_nr: int):
    for item in getattr(quotation, "items", []) or []:
        if int(item.pos_nr) == int(pos_nr):
            return item
    return None


def _current_manual_unit_price(
    *,
    pos_nr: int,
    fallback: float,
) -> float:
    overrides = st.session_state.get("manual_discount_overrides") or []

    for override in reversed(overrides):
        if (
            override.get("target") == "pos"
            and int(override.get("pos_nr", -1)) == int(pos_nr)
            and override.get("mode") == "unit_price_eur"
        ):
            return float(override.get("unit_price_eur", fallback))

    return fallback


def _invalidate_approval_after_price_change() -> None:
    """Price changes make an existing approval stale."""
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        return

    try:
        from pathlib import Path
        from quoting.api.approval_store import load_approval, transition

        review_dir = Path(review_dir_raw)
        record = load_approval(review_dir)

        if record.state in {"approved", "ready_to_send"}:
            transition(
                review_dir,
                target="reviewed",
                actor=record.approved_by,
                changed_fields=sorted(st.session_state.get("changed_fields") or []),
            )
    except Exception:
        return
    