"""Vollbild (full-screen) handling for step 3.

Driven entirely by the URL parameter ``?focus=1``. Toggling is purely
a CSS overlay — the widget tree underneath the focus shell is left
untouched, so state survives the round trip. Entering and exiting
focus mode just rewrites the URL and triggers a Streamlit rerun.

This module owns:

* The query-param check (``is_focus_mode``).
* The enter / exit helpers.
* The slim toolbar shown at the top of the focus view (a chip with
  the review-id and an "exit" button).
"""
from __future__ import annotations

import streamlit as st


# ----------------------------------------------------------- toggle
def is_focus_mode() -> bool:
    """True when the user opened step 3 in fullscreen comparison view."""
    value = st.query_params.get("focus")
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value or "").strip() in {"1", "true", "yes", "on"}


def enter_focus_mode() -> None:
    st.query_params["focus"] = "1"
    st.rerun()


def exit_focus_mode() -> None:
    if "focus" in st.query_params:
        del st.query_params["focus"]
    st.rerun()


# ----------------------------------------------------------- toolbar
def render_focus_toolbar(review_input) -> None:
    """Slim header inside Vollbild: review-id chip + exit button.

    Layout pattern: a flex container with explicit 38px height so the
    Streamlit button on the right (also ~38px tall) lines up with the
    chip on the left.
    """
    review_id = review_input.review_id or review_input.content_hash
    file_name = review_input.input_path.name if review_input.input_path else ""

    col_label, col_exit = st.columns([6, 1], vertical_alignment="center")

    with col_label:
        parts = [
            (
                '<span style="font-family:Inter Tight,Inter,sans-serif;'
                'font-weight:700;font-size:14px;color:#0f172a;'
                'letter-spacing:-0.01em;">Vergleich · Vollbild</span>'
            ),
            (
                '<span style="font-family:ui-monospace,SFMono-Regular,Consolas,monospace;'
                'font-size:11.5px;color:#64748b;background:#f5f5f4;'
                'border:1px solid #e5e7eb;padding:2px 9px;border-radius:999px;'
                f'white-space:nowrap;">{_safe_html(review_id)}</span>'
            ),
        ]
        if file_name:
            parts.append(
                '<span style="font-size:12px;color:#64748b;font-weight:500;'
                'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                'min-width:0;">'
                f'{_safe_html(file_name)}</span>'
            )

        chip_html = (
            '<div style="display:flex;align-items:center;gap:12px;'
            'height:38px;padding:0 14px;background:#ffffff;'
            'border:1px solid #e5e7eb;border-radius:10px;'
            'box-shadow:0 1px 2px rgba(15,23,42,0.04);'
            'box-sizing:border-box;overflow:hidden;'
            'margin:0;">'
            + "".join(parts)
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
            exit_focus_mode()


def _safe_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
