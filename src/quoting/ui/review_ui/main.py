"""Streamlit entry point for the quoting review UI.

Three top-level pages, selected by query params:

- **Settings** (``?settings=1``)
- **Review-Detail** (``?review_id=…``)
- **Dashboard** (no params, default)

Three human-task steps inside the Review-Detail page:

1. Positionen prüfen        → :mod:`quoting.ui.review_ui.steps.positions_step`
2. Kundendaten prüfen        → :mod:`quoting.ui.review_ui.steps.customer_step`
3. Angebot vergleichen & freigeben → :mod:`quoting.ui.review_ui.steps.approval_step`

Step 3 has an optional Vollbild toggle (``&focus=1``) that hides the
sidebar, breadcrumb, step indicator, KPI strip and agent chat so the
reviewer can focus on the side-by-side comparison and approval.

Performance notes
-----------------
Matching results are cached at the UI layer keyed by the Anfrage's
content hash. Streamlit reruns are extremely chatty (every keystroke
is a rerun), so re-running rapidfuzz against a few thousand stammdaten
rows on every keystroke was wasteful.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import streamlit as st


def _ensure_project_path() -> None:
    """Allow running this file directly via ``streamlit run``."""
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[4]
    src_dir = this_file.parents[3]
    for p in (project_root, src_dir):
        path = str(p)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


if __name__ == "__main__":
    for name in list(sys.modules):
        if name == "quoting" or name.startswith("quoting."):
            del sys.modules[name]


def _configure_page() -> None:
    st.set_page_config(
        page_title="ElringKlinger · Quoting",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# ----------------------------------------------------------- matching cache
def _matches_cache_key(anfrage, stammdaten_count: int, fuzzy: int, semantic: int) -> str:
    """Stable cache key combining the Anfrage and matching parameters."""
    payload = anfrage.model_dump(mode="json")
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    blob += f"|{stammdaten_count}|{fuzzy}|{semantic}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


def _run_matching_cached(anfrage, stammdaten, fuzzy: int, semantic: int):
    """Cache matching results across Streamlit reruns."""
    from quoting.pipeline import MatchingStep, PythonMatcher, StepContext

    cache: dict = st.session_state.setdefault("_matches_cache", {})
    key = _matches_cache_key(anfrage, len(stammdaten), fuzzy, semantic)
    cached = cache.get(key)
    if cached is not None:
        return cached

    step = MatchingStep(
        matcher=PythonMatcher(
            fuzzy_threshold=fuzzy,
            semantic_threshold=semantic,
        ),
        stammdaten=stammdaten,
    )
    review_dir = st.session_state.get("review_dir")
    work_dir = Path(review_dir) if review_dir else Path("/tmp")
    work_dir.mkdir(parents=True, exist_ok=True)
    matches = step.run(anfrage, StepContext(work_dir=work_dir))

    if len(cache) > 8:
        cache.clear()
    cache[key] = matches
    return matches


# --------------------------------------------------------------------- run
def run() -> None:
    _ensure_project_path()
    _configure_page()

    from quoting.ui.review_ui.dashboard import render_dashboard
    from quoting.ui.review_ui.focus_mode import is_focus_mode
    from quoting.ui.review_ui.layout import (
        apply_focus_style,
        apply_style,
        render_sidebar_dashboard,
        render_sidebar_settings,
    )
    from quoting.ui.review_ui.review_context import (
        REVIEWS_ROOT,
        ReviewInput,
        get_review_id_from_query,
        store_review_context,
    )
    from quoting.ui.review_ui.settings_page import render_settings_page
    from quoting.ui.review_ui.upload import handle_upload

    apply_style()

    if _is_settings_view():
        uploaded = render_sidebar_settings()
        if uploaded is not None:
            input_path, content_hash, payload = handle_upload(uploaded)
            review_input = ReviewInput(
                input_path=input_path,
                content_hash=content_hash,
                payload=payload,
                uploaded_name=uploaded.name,
            )
            store_review_context(review_input)
            st.query_params.clear()
            st.query_params["review_id"] = content_hash
            st.rerun()
        render_settings_page()
        return

    review_id = get_review_id_from_query()
    if not review_id:
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
            st.query_params["review_id"] = content_hash
            st.rerun()
        render_dashboard(REVIEWS_ROOT)
        return

    if is_focus_mode():
        apply_focus_style()
    _render_review_detail(review_id)


def _is_settings_view() -> bool:
    value = st.query_params.get("settings")
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value or "").strip() in {"1", "true", "yes", "on"}


# ----------------------------------------------------------- review detail
def _render_review_detail(review_id: str) -> None:
    """Render a single review's editing flow (steps 1 → 2 → 3)."""
    from quoting.api.settings_store import load_user_settings
    from quoting.ui.review_ui.extraction import (
        detect_and_store_agent_language,
        load_anfrage_once,
    )
    from quoting.ui.review_ui.focus_mode import is_focus_mode
    from quoting.ui.review_ui.layout import render_sidebar_review
    from quoting.ui.review_ui.nav import (
        get_step,
        render_reset_button,
        render_step_indicator,
        reset_step,
    )
    from quoting.ui.review_ui.pipeline_progress import (
        is_review_failed,
        is_review_processing,
        read_review_progress,
        render_pipeline_progress,
    )
    from quoting.ui.review_ui.quotation_flow import (
        hydrate_existing_review_state,
    )
    from quoting.ui.review_ui.resources import get_pipeline
    from quoting.ui.review_ui.review_actions import reset_pipeline
    from quoting.ui.review_ui.review_context import (
        ReviewInput,
        load_review_input,
        store_review_context,
    )
    from quoting.ui.review_ui.review_overview import render_review_title
    from quoting.ui.review_ui.state import reset_review_state
    from quoting.ui.review_ui.steps import (
        render_approval_step,
        render_customer_step,
        render_positions_step,
    )
    from quoting.ui.review_ui.steps.approval_step import (
        render_approval_step_focus,
    )
    from quoting.ui.review_ui.upload import lookup_uploaded_review

    last_id = st.session_state.get("_active_review_id")
    if last_id != review_id:
        reset_step()
        reset_review_state()
        st.session_state.pop("_matches_cache", None)
        st.session_state["_active_review_id"] = review_id
        if "focus" in st.query_params:
            del st.query_params["focus"]

    review_input: ReviewInput | None = None
    try:
        review_input = load_review_input(review_id)
    except (FileNotFoundError, ValueError):
        review_input = lookup_uploaded_review(review_id)

    if review_input is None:
        st.error(
            f"Review **{review_id}** wurde nicht gefunden. "
            "Möglicherweise wurde sie verschoben oder nie gespeichert."
        )
        if st.button("← Zurück zur Übersicht"):
            st.query_params.clear()
            st.rerun()
        return

    app_settings = load_user_settings()

    sidebar_actions = None
    if review_input.review_id and review_input.review_dir is not None:
        def sidebar_actions() -> None:
            render_reset_button(
                review_id=review_input.review_id,
                on_confirmed=lambda: reset_pipeline(
                    review_input.review_dir, review_input.review_id,
                ),
                confirm=app_settings.workflow.confirm_before_reset,
            )

    store_review_context(review_input)

    focus = is_focus_mode()
    render_sidebar_review(action_renderer=sidebar_actions)

    progress = read_review_progress(review_input.work_dir)
    if is_review_processing(progress) or is_review_failed(progress):
        if not focus:
            render_review_title(review_input.review_id, review_input.input_path)
        render_pipeline_progress(progress)
        return

    if not focus:
        render_review_title(review_input.review_id, review_input.input_path)
        render_step_indicator()
        st.markdown("&nbsp;", unsafe_allow_html=True)

    try:
        anfrage = load_anfrage_once(
            review_input.content_hash,
            review_input.input_path,
            review_input.work_dir,
        )
    except Exception as e:
        st.error(f"Fehler bei der Extraktion: {e}")
        return

    detect_and_store_agent_language(
        review_input.content_hash, review_input.input_path, anfrage,
    )

    pipeline = get_pipeline()
    matches = _run_matching_cached(
        anfrage,
        pipeline.stammdaten,
        app_settings.matching.fuzzy_threshold,
        app_settings.matching.semantic_threshold,
    )

    review_input.work_dir.mkdir(parents=True, exist_ok=True)
    hydrate_existing_review_state(
        content_hash=review_input.content_hash, matches=matches,
    )

    active = get_step()
    if focus and active != 3:
        # Focus mode is only meaningful on step 3; bail back to normal view.
        if "focus" in st.query_params:
            del st.query_params["focus"]
        st.rerun()
        return

    if focus:
        render_approval_step_focus(review_input, anfrage, matches)
        return

    if active == 1:
        render_positions_step(review_input, anfrage, matches)
    elif active == 2:
        render_customer_step(review_input, anfrage, matches)
    else:
        render_approval_step(review_input, anfrage, matches)


if __name__ == "__main__":
    run()
