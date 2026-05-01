"""Step 3 — Angebot vergleichen & freigeben.

Has two variants:

* :func:`render_approval_step` — full version with overview, compare
  panes, approval panel, agent chat and step nav.
* :func:`render_approval_step_focus` — Vollbild variant: only the
  toolbar, the compare panes and the approval panel. Sidebar,
  breadcrumb and KPI strip are hidden via the focus stylesheet.

Both variants share the same approval / refresh wiring; they only
differ in chrome.
"""
from __future__ import annotations

import streamlit.components.v1 as components
import streamlit as st

from quoting.ui.review_ui.agent_chat import render_agent_chat
from quoting.ui.review_ui.approval_panel import render_approval_panel
from quoting.ui.review_ui.compare_view import render_compare_panes
from quoting.ui.review_ui.document_view import has_real_attachment
from quoting.ui.review_ui.focus_mode import enter_focus_mode, render_focus_toolbar
from quoting.ui.review_ui.nav import render_step_nav
from quoting.ui.review_ui.quotation_flow import (
    finalize_pdf,
    maybe_auto_refresh,
    render_generate_button,
)
from quoting.ui.review_ui.review_overview import render_review_overview

# --------------------------------------------------------------- standard view
def render_approval_step(review_input, anfrage, matches) -> None:
    """Full approval step: overview → compare → approval → chat."""
    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    if not st.session_state.get("quotation"):
        _render_no_quotation_yet(review_input, anfrage, matches)
        return

    render_review_overview(
        review_id=review_input.review_id,
        input_path=review_input.input_path,
        anfrage=anfrage,
        matches=matches,
    )
    st.markdown("&nbsp;", unsafe_allow_html=True)

    has_attachment = has_real_attachment(review_input)
    is_approved = _is_approved()

    col_label, col_btn = st.columns([6, 1], vertical_alignment="center")
    with col_label:
        st.markdown(
            '<div class="ek-section-label" style="margin-bottom:0;">'
            "Vergleich"
            "</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button(
            "⛶  Vollbild",
            key="enter_focus",
            help="Original und Angebot im Vollbild vergleichen",
            use_container_width=True,
        ):
            enter_focus_mode()

    st.caption(
        "Bei Fehlern → zurück zu Schritt 1 (Positionen) oder "
        "Schritt 2 (Kunde)."
    )
    render_compare_panes(
        review_input,
        has_attachment=has_attachment,
        is_approved=is_approved,
    )

    st.markdown("---")

    if review_input.review_dir is not None:
        st.markdown(
            '<div class="ek-section-label">Freigabe</div>',
            unsafe_allow_html=True,
        )
        render_approval_panel(
            review_dir=review_input.review_dir,
            on_finalize_pdf=lambda: finalize_pdf(
                anfrage=anfrage,
                matches=matches,
                content_hash=review_input.content_hash,
            ),
        )
        st.markdown("---")

    with st.expander("Letzte Anpassungen am Preis (Agent-Chat)", expanded=False):
        render_agent_chat(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )

    st.markdown("---")
    render_step_nav(
        on_finish=_on_finish,
        finish_label="Fertig — zurück zu Outlook",
    )


# --------------------------------------------------------------- focus view
def render_approval_step_focus(review_input, anfrage, matches) -> None:
    """Step 3 in Vollbild — comparison + approval, nothing else."""
    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    if not st.session_state.get("quotation"):
        render_focus_toolbar(review_input)
        st.warning(
            "Es wurde noch kein Angebotsentwurf erzeugt. "
            "Klicke unten auf „Entwurf-Angebot erstellen“, um ihn zu generieren.",
        )
        render_generate_button(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
            uploaded_name=review_input.uploaded_name,
        )
        return

    render_focus_toolbar(review_input)
    has_attachment = has_real_attachment(review_input)
    is_approved = _is_approved()

    render_compare_panes(
        review_input,
        has_attachment=has_attachment,
        is_approved=is_approved,
    )

    st.markdown("---")

    if review_input.review_dir is not None:
        render_approval_panel(
            review_dir=review_input.review_dir,
            on_finalize_pdf=lambda: finalize_pdf(
                anfrage=anfrage,
                matches=matches,
                content_hash=review_input.content_hash,
            ),
        )


# --------------------------------------------------------------- internals
def _render_no_quotation_yet(review_input, anfrage, matches) -> None:
    st.warning(
        "Es wurde noch kein Angebotsentwurf erzeugt. "
        "Klicke unten auf „Entwurf-Angebot erstellen“, um ihn zu generieren.",
    )
    render_generate_button(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
        uploaded_name=review_input.uploaded_name,
    )
    st.markdown("---")
    render_step_nav(can_advance=False)


def _is_approved() -> bool:
    """True if the current review's approval-state is approved or beyond."""
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        return False
    try:
        from pathlib import Path
        from quoting.api.approval_store import load_approval
        record = load_approval(Path(review_dir_raw))
        return record.state in ("approved", "ready_to_send")
    except Exception:
        return False


def _on_finish() -> None:
    """Try to close the tab (Outlook flow) or redirect to dashboard."""
    components.html(
        """
        <script>
          (function () {
            try { window.close(); } catch (e) {}
            setTimeout(function () {
              if (!window.closed) {
                window.location.href = window.location.pathname;
              }
            }, 250);
          })();
        </script>
        """,
        height=0,
    )
    st.success(
        "Workflow abgeschlossen. Falls dieses Fenster nicht automatisch "
        "schließt, kannst du es jetzt schließen und zu Outlook zurückkehren.",
    )
