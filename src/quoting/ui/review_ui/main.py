"""Streamlit entry point for the quoting review UI.

Three top-level pages, selected by query params:

- **Settings** (``?settings=1``)
  Global config — company profile, fuzzy threshold, workflow toggles.

- **Review-Detail** (``?review_id=…``)
  Single-active-step layout for a specific review. Three human-task
  steps:
    1. Positionen prüfen (positions + matching)
    2. Kundendaten prüfen (customer header + commercial terms)
    3. Angebot vergleichen & freigeben (side-by-side with draft PDF)

- **Dashboard** (no params, default)
  List of all reviews with KPIs and insights.

Step labels are shared with the Outlook plugin via :mod:`nav`.
"""
from __future__ import annotations

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
    render_header()

    # ------- Settings page ----------------------------------------------
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

    # ------- Dashboard mode ---------------------------------------------
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

    # ------- Review-detail mode -----------------------------------------
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

    # If the review_id changed since last render, clear ALL session state.
    last_id = st.session_state.get("_active_review_id")
    if last_id != review_id:
        reset_step()
        reset_review_state()
        st.session_state["_active_review_id"] = review_id

    # ----- input resolution -------------------------------------------------
    review_input: ReviewInput | None = None
    try:
        review_input = load_review_input(review_id)
    except (FileNotFoundError, ValueError):
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
    render_sidebar_review(
        review_id=review_input.review_id or review_id,
        action_renderer=sidebar_actions,
    )

    # ----- pipeline progress -----------------------------------------------
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

    # ----- single active step ---------------------------------------------
    active = get_step()
    if active == 1:
        _render_step_one(review_input, anfrage, matches)
    elif active == 2:
        _render_step_two(review_input, anfrage, matches)
    else:
        _render_step_three(review_input, anfrage, matches)


# ----------------------------------------------------------- step renders

def _render_step_one(review_input, anfrage, matches) -> None:
    """Step 1 — Positionen prüfen.

    Layout:
        [ Original-Anfrage ]   |   [ Positionen + Matching ]
                               ↓
                        ✓ Positionen bestätigen
    """
    from quoting.ui.review_ui.document_view import (
        render_mail_body_pane,
        render_original_request,
    )
    from quoting.ui.review_ui.editor import render_positions_editor
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import maybe_auto_refresh

    col_doc, col_review = st.columns([1, 1], gap="large")

    with col_review:
        render_positions_editor(anfrage, matches)

    # Build the refreshed draft in the background so step 3 already
    # has a current PDF when the user gets there.
    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    with col_doc:
        if _is_mail_body_only(review_input):
            render_mail_body_pane(
                body=_load_mail_body(review_input.input_path),
                subject=anfrage.kunde_firma or review_input.input_path.name,
                sender=anfrage.kunde_email or "",
            )
        else:
            render_original_request(
                review_input.input_path,
                review_input.payload,
                show_draft_toggle=False,
            )

    st.markdown("---")
    render_step_nav(
        can_advance=True,
        forward_label="✓ Positionen bestätigen",
    )


def _render_step_two(review_input, anfrage, matches) -> None:
    """Step 2 — Kundendaten prüfen.

    Layout:
        [ Original-Anfrage ]   |   [ Kundendaten / Header / Firma ]
                               ↓
                        ✓ Kundendaten bestätigen
    """
    from quoting.ui.review_ui.document_view import (
        render_mail_body_pane,
        render_original_request,
    )
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
        if _is_mail_body_only(review_input):
            render_mail_body_pane(
                body=_load_mail_body(review_input.input_path),
                subject=anfrage.kunde_firma or review_input.input_path.name,
                sender=anfrage.kunde_email or "",
            )
        else:
            render_original_request(
                review_input.input_path,
                review_input.payload,
                show_draft_toggle=False,
            )

    st.markdown("---")
    render_step_nav(
        can_advance=True,
        forward_label="✓ Kundendaten bestätigen",
    )


def _render_step_three(review_input, anfrage, matches) -> None:
    """Step 3 — Angebot vergleichen & freigeben.

    Layout:
        [ Zusammenfassung / KPIs ]
        ─────────────────────────────────────────────
        Tabs: ↔️ Vergleich | 📄 Original | ✨ Entwurf
        ─────────────────────────────────────────────
        [ Freigabe-Workflow ]
        [ Agent-Chat (collapsed) ]
        ─────────────────────────────────────────────
        ← Zurück  |  ✓ Workflow abschließen
    """
    from quoting.ui.review_ui.agent_chat import render_agent_chat
    from quoting.ui.review_ui.approval_panel import render_approval_panel
    from quoting.ui.review_ui.document_view import (
        render_draft_pdf_pane,
        render_mail_body_pane,
        render_original_request,
    )
    from quoting.ui.review_ui.nav import render_step_nav
    from quoting.ui.review_ui.quotation_flow import (
        finalize_pdf,
        maybe_auto_refresh,
        render_generate_button,
    )
    from quoting.ui.review_ui.review_overview import render_review_overview

    # Make sure the draft is up to date before we show it.
    maybe_auto_refresh(
        anfrage=anfrage,
        matches=matches,
        content_hash=review_input.content_hash,
    )

    # If there's no draft yet, surface the generate button as the first
    # thing the user sees and gate progression.
    if not st.session_state.get("quotation"):
        st.warning(
            "Es wurde noch kein Angebotsentwurf erzeugt. "
            "Klicke unten auf „Entwurf-Angebot erstellen“, um ihn zu generieren.",
            icon="⚠️",
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

    # ----- KPI strip -------------------------------------------------------
    render_review_overview(
        review_id=review_input.review_id,
        input_path=review_input.input_path,
        anfrage=anfrage,
        matches=matches,
    )

    st.markdown("&nbsp;", unsafe_allow_html=True)

    # ----- comparison view -------------------------------------------------
    st.markdown(
        '<div class="ek-section-label">Originaleingang ↔ Angebotsentwurf</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Wechsle zwischen Side-by-side-Vergleich und Vollansicht. "
        "Bei Fehlern → zurück zu Schritt 1 (Positionen) oder Schritt 2 (Kunde)."
    )

    tab_split, tab_orig, tab_draft = st.tabs([
        "↔️ Vergleich (beide)",
        "📄 Original",
        "✨ Angebotsentwurf",
    ])

    def _draw_original():
        if _is_mail_body_only(review_input):
            render_mail_body_pane(
                body=_load_mail_body(review_input.input_path),
                subject=anfrage.kunde_firma or review_input.input_path.name,
                sender=anfrage.kunde_email or "",
            )
        else:
            render_original_request(
                review_input.input_path,
                review_input.payload,
                show_draft_toggle=False,
            )

    with tab_split:
        col_orig, col_draft = st.columns(2, gap="large")
        with col_orig:
            _draw_original()
        with col_draft:
            render_draft_pdf_pane()

    with tab_orig:
        _draw_original()

    with tab_draft:
        render_draft_pdf_pane()

    st.markdown("---")

    # ----- approval workflow -----------------------------------------------
    if review_input.review_dir is not None:
        st.markdown(
            '<div class="ek-section-label">Freigabe-Workflow</div>',
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

    # ----- optional agent chat (collapsed) ---------------------------------
    with st.expander("💬 Letzte Anpassungen am Preis (Agent-Chat)", expanded=False):
        render_agent_chat(
            anfrage=anfrage,
            matches=matches,
            content_hash=review_input.content_hash,
        )

    st.markdown("---")
    render_step_nav(
        on_finish=_on_finish,
        finish_label="✓ Workflow abschließen",
    )


def _on_finish() -> None:
    """Final action when the user clicks 'Workflow abschließen'."""
    st.success(
        "Review abgeschlossen. Das PDF kann jetzt aus Outlook versendet werden.",
        icon="✅",
    )
    if st.button("Zur Übersicht"):
        st.query_params.clear()
        st.rerun()


# ----------------------------------------------------------- helpers

def _is_mail_body_only(review_input) -> bool:
    """True if the review input is a mail with no real attachment payload."""
    suffix = review_input.input_path.suffix.lower()
    if suffix not in {".eml", ".msg"}:
        return False
    try:
        from quoting.ingestion import parse_mail
        mail = parse_mail(review_input.input_path)
        return not mail.attachments
    except Exception:
        return False


def _load_mail_body(input_path: Path) -> str:
    try:
        from quoting.ingestion import parse_mail
        return parse_mail(input_path).body or ""
    except Exception:
        return ""


def _reset_pipeline(review_dir: Path, review_id: str) -> None:
    """Locally reset a review and re-run the pipeline.

    Mirrors what the API endpoint does — used for in-process resets
    triggered from the Streamlit UI without a round-trip through the
    HTTP layer. Keeps mail.json + listed attachments, wipes everything
    else, then re-runs in the foreground (it's fast enough).
    """
    from quoting.api.approval_store import reset_approval
    from quoting.api.progress_store import init_progress
    from quoting.ingestion import Mail
    from quoting.ui.review_ui.resources import get_pipeline
    from quoting.ui.review_ui.state import reset_review_state
    import json

    if not review_dir.exists():
        st.error("Review-Verzeichnis nicht mehr verfügbar.")
        return

    # Identify mail.json + saved attachments to preserve
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

    # Wipe everything else
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

    # Re-run pipeline using the saved mail
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

    st.success("Pipeline wurde neu ausgeführt.", icon="🔄")
    st.rerun()


if __name__ == "__main__":
    run()
