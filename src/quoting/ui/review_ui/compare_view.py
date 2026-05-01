"""Side-by-side comparison panes for step 3.

Renders the two columns the reviewer compares: the original input
(file + optional mail body) on the left, and the AI-produced quotation
(draft + optional final PDF) on the right.

Both columns use parallel ``st.tabs`` so the inner viewers — PDF iframe,
dataframe, mail body — start at the same vertical height. The original
side carries 1 or 2 tabs depending on whether the request had a mail
body; the angebot side carries 1 tab before approval (``Entwurf``) and
2 tabs after (``Entwurf`` + ``Final``). The "final" tab disappears the
moment the user revokes approval.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from quoting.ui.review_ui.document_view import (
    render_input_file_only,
    render_mail_body_only,
    render_specific_pdf,
)


@contextmanager
def comparison_viewer_pair():
    """Mark viewer renderers as part of the side-by-side comparison.

    Some inner renderers (PDF iframes, mail body shells) tighten their
    layout when this flag is set so the two columns line up cleanly.
    """
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


def render_compare_panes(
    review_input,
    *,
    has_attachment: bool,
    is_approved: bool,
) -> None:
    """Render the two compare columns with parallel tab strips."""
    has_mail = _has_mail_body(review_input)
    file_label = _short_file_label(review_input.input_path)

    if has_attachment and has_mail:
        orig_tabs = [file_label, "Mail-Text"]
    elif has_attachment:
        orig_tabs = [file_label]
    else:
        orig_tabs = ["Mail-Text"]

    angebot_tabs = ["Entwurf", "Finales Angebot"] if is_approved else ["Entwurf"]

    with comparison_viewer_pair():
        col_orig, col_draft = st.columns(2, gap="large")

        with col_orig:
            st.markdown(
                '<div class="ek-compare-pane-label">Original</div>',
                unsafe_allow_html=True,
            )
            tabs = st.tabs(orig_tabs)
            tab_index = 0
            if has_attachment:
                with tabs[tab_index]:
                    render_input_file_only(review_input)
                tab_index += 1
            if has_mail:
                with tabs[tab_index]:
                    render_mail_body_only(review_input)

        with col_draft:
            label_html = (
                '<div class="ek-compare-pane-label '
                'ek-compare-pane-label-approved">'
                'Angebot · '
                '<span class="ek-compare-pane-badge ek-compare-pane-badge-success">'
                'freigegeben</span></div>'
                if is_approved
                else '<div class="ek-compare-pane-label">Angebotsentwurf</div>'
            )
            st.markdown(label_html, unsafe_allow_html=True)
            tabs = st.tabs(angebot_tabs)
            with tabs[0]:
                render_specific_pdf(kind="draft")
            if is_approved and len(tabs) > 1:
                with tabs[1]:
                    render_specific_pdf(kind="final")


# --------------------------------------------------------------------- helpers
def _has_mail_body(review_input) -> bool:
    """True if mail.json has a non-empty body for this review."""
    if review_input.review_dir is None:
        return False
    from quoting.reviews import load_mail_meta
    meta = load_mail_meta(review_input.review_dir)
    if not isinstance(meta, dict):
        return False
    return bool((meta.get("body") or "").strip())


def _short_file_label(input_path: Path | None) -> str:
    """Compact tab label — suffix prefix + filename, capped for readability."""
    if input_path is None:
        return "Datei"
    suffix = input_path.suffix.upper().lstrip(".")
    name = input_path.name
    if len(name) > 40:
        name = name[:37] + "…"
    if not suffix:
        return name
    return f"{suffix} · {name}"
