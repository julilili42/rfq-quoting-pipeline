"""Shared step vocabulary + navigation widgets.

Three human-task steps inside the Review UI:

    1. Positionen prüfen
    2. Kundendaten prüfen
    3. Angebot vergleichen & freigeben

Navigation strategy
-------------------
The visual step indicator is a row of clickable chips. Completed steps
act as quick "jump back" links — no separate button row beneath, no
emoji, no heavy Streamlit primary buttons. Forward progression goes
through the bottom nav bar's primary action.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st


# ---------- shared step vocabulary -----------------------------------------

@dataclass(frozen=True)
class Step:
    num: int
    title: str
    description: str


STEPS: tuple[Step, ...] = (
    Step(
        1,
        "Positionen prüfen",
        "KI-extrahierte Positionen kontrollieren und Stammdaten-Treffer "
        "validieren.",
    ),
    Step(
        2,
        "Kundendaten prüfen",
        "Empfänger, Ansprechpartner und kommerzielle Bedingungen prüfen.",
    ),
    Step(
        3,
        "Angebot vergleichen & freigeben",
        "Angebotsentwurf mit dem Originaleingang vergleichen und freigeben.",
    ),
)


# ---------- step state -----------------------------------------------------

_STATE_KEY = "active_step"


def get_step() -> int:
    query_step = _step_from_query()
    if query_step is not None:
        st.session_state[_STATE_KEY] = query_step
        return query_step
    return int(st.session_state.get(_STATE_KEY, 1))


def set_step(n: int) -> None:
    step = max(1, min(len(STEPS), int(n)))
    st.session_state[_STATE_KEY] = step
    st.query_params["step"] = str(step)


def reset_step() -> None:
    st.session_state[_STATE_KEY] = 1
    if "step" in st.query_params:
        del st.query_params["step"]


# ---------- visual indicator ----------------------------------------------

def render_step_indicator() -> None:
    """Visual progress strip — completed steps are clickable links."""
    current = get_step()

    parts = ['<div class="ek-steps">']
    for s in STEPS:
        cls = "ek-step"
        is_done = s.num < current
        is_active = s.num == current
        clickable = is_done

        if is_done:
            cls += " done"
        elif is_active:
            cls += " active"
        if clickable:
            cls += " clickable"

        marker = "✓" if is_done else f"{s.num:02d}"
        inner = (
            f'<div class="ek-step-num">{marker}</div>'
            f'<div class="ek-step-title">{s.title}</div>'
            f'<p class="ek-step-desc">{s.description}</p>'
        )
        if clickable:
            href = f"?step={s.num}"
            parts.append(
                f'<a class="{cls}" href="{href}" target="_self">{inner}</a>'
            )
        else:
            parts.append(f'<div class="{cls}">{inner}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _step_from_query() -> int | None:
    raw = st.query_params.get("step")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    try:
        return max(1, min(len(STEPS), int(raw)))
    except (TypeError, ValueError):
        return None


# ---------- nav buttons ----------------------------------------------------

def render_step_nav(
    *,
    can_advance: bool = True,
    advance_disabled_reason: str = "",
    forward_label: str = "Weiter",
    on_finish: Callable[[], None] | None = None,
    finish_label: str = "Fertig",
) -> None:
    """Bottom navigation bar inside a step.

    - Step 1: only the forward button.
    - Step 2: both buttons.
    - Step 3: ``← Zurück`` + optional ``finish`` action.
    """
    current = get_step()
    total = len(STEPS)

    cols = st.columns([1, 2, 1])

    with cols[0]:
        if current > 1:
            if st.button(
                "← Zurück",
                key=f"_nav_back_{current}",
                use_container_width=True,
            ):
                set_step(current - 1)
                st.rerun()

    with cols[2]:
        if current < total:
            if st.button(
                forward_label,
                key=f"_nav_next_{current}",
                type="primary",
                disabled=not can_advance,
                use_container_width=True,
                help=advance_disabled_reason if not can_advance else None,
            ):
                set_step(current + 1)
                st.rerun()
        elif on_finish is not None:
            if st.button(
                finish_label,
                key=f"_nav_finish_{current}",
                type="primary",
                use_container_width=True,
            ):
                on_finish()


# ---------- reset action --------------------------------------------------

def render_reset_button(
    *,
    review_id: str,
    on_confirmed: Callable[[], None],
    confirm: bool = True,
) -> None:
    """Sidebar danger-zone reset button.

    Renders inside the sidebar's "Weitere Aktionen" expander. The
    visual treatment comes from the ``ek-sidebar-danger`` CSS in
    ``layout.py`` — a soft red accent that signals destructive action
    without screaming.
    """
    state_key = f"_reset_confirm_{review_id}"
    pending = st.session_state.get(state_key, False)

    st.markdown(
        '<div class="ek-sidebar-danger">'
        '<div class="ek-sidebar-danger-title">Pipeline neu starten</div>'
        '<div class="ek-sidebar-danger-desc">'
        "Verarbeitet die Anfrage komplett neu. Alle bisherigen "
        "Anpassungen gehen verloren, Anhänge bleiben erhalten."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if not confirm:
        if st.button(
            "Neu starten",
            key=f"_reset_{review_id}",
            use_container_width=True,
        ):
            on_confirmed()
        return

    if not pending:
        if st.button(
            "Neu starten",
            key=f"_reset_{review_id}",
            use_container_width=True,
        ):
            st.session_state[state_key] = True
            st.rerun()
        return

    st.markdown(
        '<div class="ek-sidebar-danger-confirm">'
        "Wirklich neu starten? Diese Aktion kann nicht rückgängig "
        "gemacht werden."
        "</div>",
        unsafe_allow_html=True,
    )
    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button(
            "Ja, neu starten",
            type="primary",
            key=f"_reset_yes_{review_id}",
            use_container_width=True,
        ):
            st.session_state[state_key] = False
            on_confirmed()
    with col_cancel:
        if st.button(
            "Abbrechen",
            key=f"_reset_no_{review_id}",
            use_container_width=True,
        ):
            st.session_state[state_key] = False
            st.rerun()
