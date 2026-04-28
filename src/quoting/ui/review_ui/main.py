"""Streamlit entry point for the quoting review UI.

Two top-level pages:

- **Dashboard** (default, no ``review_id`` query param)
  Lists all reviews, statistics, search/filter.

- **Review-Detail** (``?review_id=…``)
  Single-active-step layout: each step shows just its own content,
  ``← Zurück / Weiter →`` buttons make the linear flow explicit.

Step labels are shared with the Outlook plugin via :mod:`nav`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


def _ensure_project_path() -> None:
    """Allow running this file directly via ``streamlit run``."""
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[4]
    src_dir = this_file.parents[3]
    for p in (project_root, src_dir):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _configure_page() -> None:
    st.set_page_config(
        page_title="ElringKlinger · Quoting",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# --------------------------------------------------------------------- run

def run() -> None:
    _ensure_project_path()
    _configure_page()

    # Imports kept inside run() so streamlit hot-reload picks up edits.
    from quoting.ui.review_ui.dashboard import render_dashboard
    from quoting.ui.review_ui.layout import (
        apply_style,
        render_header,
        render_sidebar_dashboard,
    )
    from quoting.ui.review_ui.review_context import (
        REVIEWS_ROOT,
        ReviewInput,
        get_review_id_from_query,
        store_review_context,
    )
    from quoting.ui.review_ui.upload import handle_upload

    apply_style()
    render_header()

    review_id = get_review_id_from_query()

    if not review_id:
        # ----- Dashboard mode --------------------------------------------------
        uploaded = render_sidebar_dashboard()
        if uploaded is not None:
            input_path, content_hash, payload = handle_upload(uploaded)
            review_input = ReviewInput(
                input_path=input_path,
                content_hash=content_hash,
                payload=payload,
                uploaded_name=uploaded.name,
            )
            store_review_context(review_input)
            # Send the user into the review-detail flow with a synthetic id
            st.query_params["review_id"] = content_hash
            st.rerun()

        render_dashboard(REVIEWS_ROOT)
        return

    # ----- Review detail mode ----------------------------------------------
    _render_review_detail(review_id)


# ----------------------------------------------------------- review detail

def _render_review_detail(review_id: str) -> None:
    """Render a single review's editing flow (steps 1 → 2 → 3)."""
    from quoting.pipeline import MatchingStep, PythonMatcher, StepContext
    from quoting.ui.review_ui.extraction import (
        detect_and_store_agent_language,
        load_anfrage_once,
    )
    from quoting.ui.review_ui.layout import render_sidebar_review
    from quoting.ui.review_ui.nav import (
        get_step,
        render_step_indicator,
        reset_step,
    )
    from quoting.ui.review_ui.quotation_flow import hydrate_existing_review_state
    from quoting.ui.review_ui.resources import get_pipeline, settings
    from quoting.ui.review_ui.review_context import (
        ReviewInput,
        load_review_input,
        store_review_context,
    )
    from quoting.ui.review_ui.review_overview import render_review_title
    from quoting.ui.review_ui.upload import lookup_uploaded_review

    # If the review_id changed since last render, reset the step state.
    last_id = st.session_state.get("_active_review_id")
    if last_id != review_id:
        reset_step()
        st.session_state["_active_review_id"] = review_id

    # ----- input resolution -------------------------------------------------
    review_input: ReviewInput | None = None

    # 1) Try existing review folder under data/reviews/
    try:
        review_input = load_review_input(review_id)
    except (FileNotFoundError, ValueError):
        # 2) Fallback: maybe this is a freshly uploaded session (content_hash)
        review_input = lookup_uploaded_review(review_id)

    if review_input is None:
        st.error(
            f"❌ Review **{review_id}** wurde nicht gefunden. "
            "Möglicherweise wurde sie verschoben oder nie gespeichert."
        )
        if st.button("← Zurück zur Übersicht"):
            st.query_params.clear()
            st.rerun()
        return

    store_review_context(review_input)
    fuzzy_threshold = render_sidebar_review(
        review_id=review_input.review_id or review_id
    )

    from quoting.ui.review_ui.pipeline_progress import (
    is_review_failed,
    is_review_processing,
    read_review_progress,
    render_pipeline_progress,
)

    progress = read_review_progress(review_input.work_dir)

    if is_review_processing(progress) or is_review_failed(progress):
        render_review_title(review_input.review_id, review_input.input_path)
        render_pipeline_progress(progress)
        return

    # ----- hero + steps ----------------------------------------------------
    render_review_title(review_input.review_id, review_input.input_path)
    render_step_indicator()
    st.markdown("&nbsp;", unsafe_allow_html=True)

    # ----- extract once ----------------------------------------------------
    try:
        anfrage = load_anfrage_once(
            review_input.content_hash,
            review_input.input_path,
            review_input.work_dir,
        )
    except Exception as e:
        st.error(f"❌ Fehler bei der Extraktion: {e}")
        return

    detect_and_store_agent_language(
        review_input.content_hash, review_input.input_path, anfrage,
    )

    # ----- match once via the pipeline -------------------------------------
    # The slider lets the user override the fuzzy threshold per session, so
    # we build a one-off MatchingStep around it instead of using the
    # pipeline's default matcher. Stammdaten still come from the cached
    # pipeline instance.
    pipeline = get_pipeline()
    matching_step = MatchingStep(
        matcher=PythonMatcher(
            fuzzy_threshold=fuzzy_threshold,
            semantic_threshold=settings().semantic_threshold,
        ),
        stammdaten=pipeline.stammdaten,
    )
    review_input.work_dir.mkdir(parents=True, exist_ok=True)
    ctx = StepContext(work_dir=review_input.work_dir)
    matches = matching_step.run(anfrage, ctx)

    hydrate_existing_review_state(
        content_hash=review_input.content_hash, matches=matches,
    )

    # ----- single active step ---------------------------------------------
    active = get_step()
    if active == 1:
        _render_step_one(review_input, anfrage)
    elif active == 2:
        _render_step_two(review_input, anfrage, matches)
    else:
        _render_step_three(review_input, anfrage, matches)

    st.markdown("---")


def _render_step_one(review_input, anfrage) -> None:
    """Step 1 — Anfrage analysieren."""
    from quoting.ui.review_ui.document_view import render_original_request
    from quoting.ui.review_ui.editor import render_editor
    from quoting.ui.review_ui.nav import render_step_nav

    col_doc, col_extract = st.columns([1, 1], gap="large")
    with col_doc:
        render_original_request(review_input.input_path, review_input.payload)
    with col_extract:
        render_editor(anfrage)

    st.markdown("---")
    render_step_nav(can_advance=True)


def _render_step_two(review_input, anfrage, matches) -> None:
    """Step 2 — Angebot erstellen."""
    from quoting.ui.review_ui.matching_view import render_matching
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import render_generate_button
    from quoting.ui.review_ui.review_overview import render_review_overview

    render_review_overview(
        review_id=review_input.review_id,
        input_path=review_input.input_path,
        anfrage=anfrage,
        matches=matches,
    )
    st.markdown("---")
    render_matching(anfrage, matches)

    st.markdown("---")
    render_generate_button(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
        uploaded_name=review_input.uploaded_name,
    )

    has_quotation = bool(st.session_state.get("quotation"))
    st.markdown("---")
    render_step_nav(
        can_advance=has_quotation,
        advance_disabled_reason=(
            "Bitte erst ein Angebots-PDF generieren, dann zu Schritt 3."
        ),
    )


def _render_step_three(review_input, anfrage, matches) -> None:
    """Step 3 — Angebot versenden."""
    from quoting.ui.review_ui.agent_chat import render_agent_chat
    from quoting.ui.review_ui.nav import render_step_nav

    if not st.session_state.get("quotation"):
        st.warning(
            "Es wurde noch kein Angebot generiert. "
            "Bitte zurück zu Schritt 2.",
            icon="⚠️",
        )
    else:
        render_agent_chat(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )

    st.markdown("---")
    render_step_nav(
        on_finish=lambda: _on_finish(),
        finish_label="✓ Workflow abschließen",
    )


def _on_finish() -> None:
    """Final action when the user clicks 'Workflow abschließen'."""
    st.success(
        "Angebot fertiggestellt. Das PDF kann jetzt aus Outlook versendet "
        "werden — die Übersicht zeigt diesen Review als abgeschlossen.",
        icon="✅",
    )
    if st.button("Zur Übersicht"):
        st.query_params.clear()
        st.rerun()


if __name__ == "__main__":
    run()
