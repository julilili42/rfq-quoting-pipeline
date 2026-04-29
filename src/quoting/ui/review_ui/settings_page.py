"""Settings page for the review UI.

Owns persistent preferences that the rest of the app reads:
- Company profile (used for PDF generation, quick-fill in editor)
- Matching preferences (fuzzy threshold)
- Workflow preferences (auto-refresh, confirmations)

Routed via ``?settings=1`` in the URL — separate from any review_id so
the user can hit "Settings" from anywhere without losing context.
"""
from __future__ import annotations

import streamlit as st

from quoting.api.settings_store import (
    AppSettings,
    CompanyProfile,
    MatchingPreferences,
    WorkflowPreferences,
    load_settings,
    save_settings,
)


def render_settings_page() -> None:
    """Top-level renderer for the settings page."""
    settings = load_settings()

    _render_hero()

    st.markdown("&nbsp;", unsafe_allow_html=True)

    new_settings = AppSettings(
        company=_render_company_block(settings.company),
        matching=_render_matching_block(settings.matching),
        workflow=_render_workflow_block(settings.workflow),
    )

    st.markdown("---")

    col_save, _ = st.columns([1, 4])
    with col_save:
        if st.button(
            "💾 Speichern",
            type="primary",
            use_container_width=True,
            key="settings_save",
        ):
            save_settings(new_settings)
            st.success("Einstellungen gespeichert.", icon="✅")
            st.toast("Einstellungen gespeichert", icon="✅")


def _render_hero() -> None:
    st.markdown(
        """
        <div class="ek-title-block">
          <h1 class="ek-title">
            Einstellungen<span class="ek-accent-dot">.</span>
          </h1>
          <p class="ek-subtitle">
            Hinterlege Firmendaten, Kontaktinformationen und
            allgemeine Angebotsstandards. Diese Werte werden automatisch
            in jedes Angebots-PDF übernommen.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_company_block(profile: CompanyProfile) -> CompanyProfile:
    st.markdown(
        '<div class="ek-section-label">🏢 Firmendaten (Absender)</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            company_name = st.text_input(
                "Firmenname",
                profile.company_name,
                placeholder="z. B. ElringKlinger Kunststofftechnik GmbH",
            )
            company_address = st.text_input(
                "Straße & Hausnummer",
                profile.company_address,
                placeholder="z. B. Industriestraße 17",
            )
            company_zip_city = st.text_input(
                "PLZ & Ort",
                profile.company_zip_city,
                placeholder="z. B. 72581 Dettingen/Erms",
            )
        with c2:
            company_country = st.text_input(
                "Land",
                profile.company_country or "Deutschland",
            )

        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown('<div class="ek-section-label">Kontaktperson für Angebote</div>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3:
            contact_person = st.text_input(
                "Name", profile.contact_person, placeholder="z. B. Max Mustermann",
            )
            contact_phone = st.text_input(
                "Telefon", profile.contact_phone, placeholder="+49 …",
            )
        with c4:
            contact_email = st.text_input(
                "E-Mail",
                profile.contact_email,
                placeholder="vertrieb@firma.de",
            )

        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown('<div class="ek-section-label">Kommerzielle Standardwerte</div>', unsafe_allow_html=True)
        c5, c6 = st.columns(2)
        with c5:
            delivery_term = st.text_input(
                "Lieferbedingung", profile.delivery_term,
                help="Standard, wenn die Anfrage nichts vorgibt.",
            )
        with c6:
            payment_term = st.text_input(
                "Zahlungsbedingung", profile.payment_term,
            )

        validity_days = st.number_input(
            "Angebotsgültigkeit (Tage)",
            min_value=1,
            max_value=365,
            value=int(profile.validity_days or 28),
            step=1,
        )

    return CompanyProfile(
        company_name=company_name,
        company_address=company_address,
        company_zip_city=company_zip_city,
        company_country=company_country,
        contact_person=contact_person,
        contact_phone=contact_phone,
        contact_email=contact_email,
        delivery_term=delivery_term,
        payment_term=payment_term,
        validity_days=int(validity_days),
    )


def _render_matching_block(prefs: MatchingPreferences) -> MatchingPreferences:
    st.markdown(
        '<div class="ek-section-label" style="margin-top: 18px;">'
        "🎯 Matching-Verhalten</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.caption(
            "Die Schwellwerte steuern, wie streng das System Artikel "
            "aus der Anfrage gegen die Stammdaten matcht. Höher = strenger. "
            "Bei OCR-Anfragen mit Tippfehlern lohnt sich ein niedrigerer Wert."
        )
        c1, c2 = st.columns(2)
        with c1:
            fuzzy_threshold = st.slider(
                "Fuzzy-Schwelle",
                min_value=50, max_value=100,
                value=int(prefs.fuzzy_threshold),
                help="Schwellwert für Tippfehler-Erkennung (Levenshtein-Ähnlichkeit).",
            )
        with c2:
            semantic_threshold = st.slider(
                "Semantische Schwelle",
                min_value=40, max_value=100,
                value=int(prefs.semantic_threshold),
                help="Schwellwert für Bezeichnung+Werkstoff-basiertes Matching.",
            )

    return MatchingPreferences(
        fuzzy_threshold=int(fuzzy_threshold),
        semantic_threshold=int(semantic_threshold),
    )


def _render_workflow_block(prefs: WorkflowPreferences) -> WorkflowPreferences:
    st.markdown(
        '<div class="ek-section-label" style="margin-top: 18px;">'
        "⚙️ Workflow</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        auto_refresh_pdf = st.toggle(
            "PDF nach jeder Änderung automatisch neu generieren",
            value=bool(prefs.auto_refresh_pdf),
            help=(
                "Wenn aktiviert, wird das PDF beim Speichern in Schritt 1 / 2 "
                "automatisch aktualisiert. Sonst muss explizit auf "
                "\"Angebot generieren\" geklickt werden."
            ),
        )
        confirm_before_reset = st.toggle(
            "Vor Reset bestätigen",
            value=bool(prefs.confirm_before_reset),
            help=(
                "Fragt nach, bevor die Pipeline für eine Anfrage komplett "
                "neu durchlaufen wird."
            ),
        )

    return WorkflowPreferences(
        auto_refresh_pdf=bool(auto_refresh_pdf),
        confirm_before_reset=bool(confirm_before_reset),
    )
