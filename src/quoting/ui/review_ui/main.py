"""Streamlit entry point for the quoting review UI.

Three top-level pages, selected by query params:
- **Settings** (``?settings=1``)
- **Review-Detail** (``?review_id=…``)
  Three human-task steps:
    1. Positionen prüfen
    2. Kundendaten prüfen
    3. Angebot vergleichen & freigeben
  Step 3 has an optional Vollbild toggle (``&focus=1``) that hides the
  sidebar, breadcrumb, step indicator, KPI strip and agent chat so the
  reviewer can focus on the side-by-side comparison and approval.
- **Dashboard** (no params, default)

Step labels are shared with the Outlook plugin via :mod:`nav`.
"""

from __future__ import annotations

from contextlib import contextmanager
import shutil
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


@contextmanager
def _viewer_expander(label: str, *, expanded: bool = True):
    """Wrap a document viewer in a Streamlit expander.

    The session flag lets nested renderers avoid creating another
    expander inside this one.
    """
    key = "_review_viewer_expander_active"
    previous = st.session_state.get(key, None)

    with st.expander(label, expanded=expanded):
        st.session_state[key] = True
        try:
            yield
        finally:
            if previous is None:
                st.session_state.pop(key, None)
            else:
                st.session_state[key] = previous


@contextmanager
def _comparison_viewer_pair():
    """Mark viewer renderers as part of the side-by-side comparison."""
    key = "_review_compare_view_active"
    previous = st.session_state.get(key, None)
    st.session_state[key] = True
    try:
        yield
    finally:
        if previous is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = previous


# ----------------------------------------------------------- focus mode

def _is_focus_mode() -> bool:
    """True when the user opened step 3 in fullscreen comparison view."""
    value = st.query_params.get("focus")
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value or "").strip() in {"1", "true", "yes", "on"}


def _enter_focus_mode() -> None:
    st.query_params["focus"] = "1"
    st.rerun()


def _exit_focus_mode() -> None:
    if "focus" in st.query_params:
        del st.query_params["focus"]
    st.rerun()


# --------------------------------------------------------------------- run

def run() -> None:
    _ensure_project_path()
    _configure_page()

    from quoting.ui.review_ui.dashboard import render_dashboard
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

    # Focus mode applies global CSS that collapses sidebar / chrome.
    if _is_focus_mode():
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
    from quoting.api.settings_store import load_settings as load_app_settings
    from quoting.pipeline import MatchingStep, PythonMatcher, StepContext
    from quoting.ui.review_ui.extraction import (
        detect_and_store_agent_language,
        load_anfrage_once,
    )
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
    from quoting.ui.review_ui.review_context import (
        ReviewInput,
        load_review_input,
        store_review_context,
    )
    from quoting.ui.review_ui.review_overview import render_review_title
    from quoting.ui.review_ui.state import reset_review_state
    from quoting.ui.review_ui.upload import lookup_uploaded_review

    last_id = st.session_state.get("_active_review_id")
    if last_id != review_id:
        reset_step()
        reset_review_state()
        st.session_state["_active_review_id"] = review_id
        # Switching reviews always exits focus mode — fresh start.
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

    app_settings = load_app_settings()

    sidebar_actions = None
    if review_input.review_id and review_input.review_dir is not None:
        def sidebar_actions() -> None:
            render_reset_button(
                review_id=review_input.review_id,
                on_confirmed=lambda: _reset_pipeline(
                    review_input.review_dir, review_input.review_id,
                ),
                confirm=app_settings.workflow.confirm_before_reset,
            )

    store_review_context(review_input)

    focus = _is_focus_mode()

    # Sidebar is always rendered — focus mode hides it via CSS so the
    # widget tree (and Streamlit's state) stays intact when toggling.
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
    matching_step = MatchingStep(
        matcher=PythonMatcher(
            fuzzy_threshold=app_settings.matching.fuzzy_threshold,
            semantic_threshold=app_settings.matching.semantic_threshold,
        ),
        stammdaten=pipeline.stammdaten,
    )

    review_input.work_dir.mkdir(parents=True, exist_ok=True)
    ctx = StepContext(work_dir=review_input.work_dir)
    matches = matching_step.run(anfrage, ctx)

    hydrate_existing_review_state(
        content_hash=review_input.content_hash, matches=matches,
    )

    active = get_step()

    # Focus mode is only meaningful on step 3. If the user is on a
    # different step somehow, drop them back into the normal layout.
    if focus and active != 3:
        _exit_focus_mode()
        return

    if focus:
        _render_step_three_focus(review_input, anfrage, matches)
        return

    if active == 1:
        _render_step_one(review_input, anfrage, matches)
    elif active == 2:
        _render_step_two(review_input, anfrage, matches)
    else:
        _render_step_three(review_input, anfrage, matches)


# ----------------------------------------------------------- step renders

def _render_step_one(review_input, anfrage, matches) -> None:
    """Step 1 — Positionen prüfen."""
    from quoting.ui.review_ui.document_view import render_input_panel
    from quoting.ui.review_ui.editor import render_positions_editor
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import maybe_auto_refresh

    col_doc, col_review = st.columns([1, 1], gap="large")
    with col_review:
        render_positions_editor(anfrage, matches)
        maybe_auto_refresh(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )
    with col_doc:
        render_input_panel(review_input)

    st.markdown("---")
    render_step_nav(
        can_advance=True,
        forward_label="Positionen bestätigen",
    )


def _render_step_two(review_input, anfrage, matches) -> None:
    """Step 2 — Kundendaten prüfen."""
    from quoting.ui.review_ui.document_view import render_input_panel
    from quoting.ui.review_ui.editor import render_customer_editor
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import maybe_auto_refresh

    col_doc, col_review = st.columns([1, 1], gap="large")
    with col_review:
        render_customer_editor(anfrage)
        maybe_auto_refresh(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )
    with col_doc:
        render_input_panel(review_input)

    st.markdown("---")
    render_step_nav(
        can_advance=True,
        forward_label="Kundendaten bestätigen",
    )


def _render_step_three(review_input, anfrage, matches) -> None:
    """Step 3 — Angebot vergleichen & freigeben.

    Layout adapts to whether there's a real attachment to compare:
    - With attachment: side-by-side tabs (Vergleich · Original · Entwurf).
    - Mail-only: side-by-side Original mail body and draft.
    """
    from quoting.ui.review_ui.agent_chat import render_agent_chat
    from quoting.ui.review_ui.approval_panel import render_approval_panel
    from quoting.ui.review_ui.document_view import (
        has_real_attachment,
        render_draft_pdf_pane,
        render_input_panel,
    )
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import (
        finalize_pdf,
        maybe_auto_refresh,
        render_generate_button,
    )
    from quoting.ui.review_ui.review_overview import render_review_overview

    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    if not st.session_state.get("quotation"):
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
        return

    render_review_overview(
        review_id=review_input.review_id,
        input_path=review_input.input_path,
        anfrage=anfrage,
        matches=matches,
    )

    st.markdown("&nbsp;", unsafe_allow_html=True)

    has_attachment = has_real_attachment(review_input)

    # Section header with inline fullscreen toggle.
    col_label, col_btn = st.columns([6, 1], vertical_alignment="center")
    with col_label:
        st.markdown(
            '<div class="ek-section-label" style="margin-bottom:0;">'
            "Originaleingang ↔ Angebotsentwurf"
            "</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button(
            "⛶  Vollbild",
            key="enter_focus",
            help="Original und Angebotsentwurf im Vollbild vergleichen",
            use_container_width=True,
        ):
            _enter_focus_mode()

    st.caption(
        "Der Vergleich öffnet Original und Angebotsentwurf gemeinsam. "
        "Bei Fehlern → zurück zu Schritt 1 (Positionen) oder Schritt 2 (Kunde)."
    )

    if has_attachment:
        tab_split, tab_orig, tab_draft = st.tabs([
            "Vergleich (beide)",
            "Original",
            "Angebotsentwurf",
        ])
        with tab_split:
            with _viewer_expander("Original und Angebotsentwurf", expanded=True):
                with _comparison_viewer_pair():
                    col_orig, col_draft = st.columns(2, gap="large")
                    with col_orig:
                        st.markdown(
                            '<div class="ek-compare-pane-label">Original</div>',
                            unsafe_allow_html=True,
                        )
                        render_input_panel(review_input, allow_mail_body_tab=False)
                    with col_draft:
                        st.markdown(
                            '<div class="ek-compare-pane-label">Angebotsentwurf</div>',
                            unsafe_allow_html=True,
                        )
                        render_draft_pdf_pane()
        with tab_orig:
            with _viewer_expander("Original", expanded=True):
                render_input_panel(review_input)
        with tab_draft:
            with _viewer_expander("Angebotsentwurf", expanded=True):
                render_draft_pdf_pane()
    else:
        with _viewer_expander("Original und Angebotsentwurf", expanded=True):
            with _comparison_viewer_pair():
                col_orig, col_draft = st.columns(2, gap="large")
                with col_orig:
                    st.markdown(
                        '<div class="ek-compare-pane-label">Original · E-Mail-Inhalt</div>',
                        unsafe_allow_html=True,
                    )
                    render_input_panel(review_input)
                with col_draft:
                    st.markdown(
                        '<div class="ek-compare-pane-label">Angebotsentwurf</div>',
                        unsafe_allow_html=True,
                    )
                    render_draft_pdf_pane()

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


def _render_step_three_focus(review_input, anfrage, matches) -> None:
    """Step 3 in Vollbild — comparison + approval, nothing else.

    Sidebar, breadcrumb, step indicator, KPI strip and the agent chat
    are all hidden so the reviewer can concentrate on comparing the
    original input with the generated draft and signing it off.
    """
    from quoting.ui.review_ui.approval_panel import render_approval_panel
    from quoting.ui.review_ui.document_view import (
        has_real_attachment,
        render_draft_pdf_pane,
        render_input_panel,
    )
    from quoting.ui.review_ui.quotation_flow import (
        finalize_pdf,
        maybe_auto_refresh,
        render_generate_button,
    )

    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    # If no draft yet, the comparison has nothing to show — fall back
    # to the normal step 3 generate-button flow.
    if not st.session_state.get("quotation"):
        _render_focus_toolbar(review_input)
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

    _render_focus_toolbar(review_input)

    has_attachment = has_real_attachment(review_input)

    with _comparison_viewer_pair():
        col_orig, col_draft = st.columns(2, gap="large")
        with col_orig:
            st.markdown(
                '<div class="ek-compare-pane-label">Original</div>',
                unsafe_allow_html=True,
            )
            render_input_panel(review_input, allow_mail_body_tab=not has_attachment)
        with col_draft:
            st.markdown(
                '<div class="ek-compare-pane-label">Angebotsentwurf</div>',
                unsafe_allow_html=True,
            )
            render_draft_pdf_pane()

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


def _render_focus_toolbar(review_input) -> None:
    """Slim header inside Vollbild: review-id chip + exit button."""
    review_id = review_input.review_id or review_input.content_hash
    file_name = review_input.input_path.name if review_input.input_path else ""

    col_label, col_exit = st.columns([6, 1], vertical_alignment="center")
    with col_label:
        chip_html = (
            f'<div class="ek-focus-bar">'
            f'  <span class="ek-focus-bar-title">Vergleich · Vollbild</span>'
            f'  <span class="ek-focus-bar-id">{_safe_html(review_id)}</span>'
            + (
                f'  <span class="ek-focus-bar-file">{_safe_html(file_name)}</span>'
                if file_name
                else ""
            )
            + "</div>"
        )
        st.markdown(chip_html, unsafe_allow_html=True)
    with col_exit:
        if st.button(
            "Vollbild verlassen",
            key="exit_focus",
            use_container_width=True,
            help="Zurück zur normalen Ansicht",
        ):
            _exit_focus_mode()


def _safe_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _on_finish() -> None:
    """Try to close the tab (Outlook flow) or redirect to dashboard."""
    import streamlit.components.v1 as components

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


# ----------------------------------------------------------- helpers

def _reset_pipeline(review_dir: Path, review_id: str) -> None:
    """Locally reset a review and re-run the pipeline."""
    from quoting.api.approval_store import reset_approval
    from quoting.api.progress_store import init_progress
    from quoting.ingestion import Mail
    from quoting.ui.review_ui.resources import get_pipeline
    from quoting.ui.review_ui.state import reset_review_state
    import json

    if not review_dir.exists():
        st.error("Review-Verzeichnis nicht mehr verfügbar.")
        return

    mail_json_path = review_dir / "mail.json"
    keep_files: set[Path] = set()
    if mail_json_path.exists():
        keep_files.add(mail_json_path)
        try:
            meta = json.loads(mail_json_path.read_text(encoding="utf-8"))
            for att in meta.get("attachments") or []:
                if isinstance(att, dict) and att.get("name"):
                    candidate = review_dir / att["name"]
                    if candidate.exists():
                        keep_files.add(candidate)
        except Exception:
            pass

    for entry in review_dir.iterdir():
        if entry in keep_files:
            continue
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
        except Exception:
            pass

    init_progress(review_dir, review_id)
    reset_approval(review_dir)
    reset_review_state()

    try:
        meta = json.loads(mail_json_path.read_text(encoding="utf-8")) \
            if mail_json_path.exists() else {}
        attachments = []
        for att in meta.get("attachments") or []:
            if isinstance(att, dict) and att.get("name"):
                p = review_dir / att["name"]
                if p.exists():
                    attachments.append(p)
        mail = Mail(
            subject=meta.get("subject", ""),
            sender=meta.get("from") or meta.get("sender", ""),
            body=meta.get("body", ""),
            attachments=attachments,
        )
        get_pipeline().run(
            mail,
            output_dir=review_dir.parent,
            work_name=review_id,
        )
    except Exception as exc:
        st.error(f"Pipeline-Reset fehlgeschlagen: {exc}")
        return

    st.success("Pipeline wurde neu ausgeführt.")
    st.rerun()


if __name__ == "__main__":
    run()
