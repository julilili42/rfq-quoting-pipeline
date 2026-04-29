"""Shared step vocabulary + navigation widgets.

The review UI uses a single-active-step layout (no tabs). The user
moves through three named human-review stages — same names that appear
in the Outlook plugin — and "Zurück" / "Weiter" buttons make the
linear flow explicit.

The three review steps are now strictly human-task-oriented:

    1. Positionen prüfen
    2. Kundendaten prüfen
    3. Angebot vergleichen & freigeben
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode

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
        "Prüfe, ob alle Positionen aus der Anfrage korrekt erkannt und "
        "den Stammdaten zugeordnet wurden.",
    ),
    Step(
        2,
        "Kundendaten prüfen",
        "Prüfe, ob die Kundendaten vollständig und korrekt übernommen wurden.",
    ),
    Step(
        3,
        "Angebot vergleichen & freigeben",
        "Vergleiche den Angebotsentwurf mit dem Originaleingang und gib ihn frei.",
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
    """Three cards showing where the user is.

    Completed steps are clickable for quick back-navigation. Current and
    future steps stay inert so reviewers must advance through the normal
    "Bestätigen" action.
    """
    current = get_step()
    parts = ['<div class="ek-steps">']
    for s in STEPS:
        cls = "ek-step"
        if s.num < current:
            cls += " done"
        elif s.num == current:
            cls += " active"

        marker = "✓" if s.num < current else f"{s.num:02d}"
        inner = (
            f'  <div class="ek-step-num">{marker}</div>'
            f'  <div class="ek-step-title">{s.title}</div>'
            f'  <p class="ek-step-desc">{s.description}</p>'
        )
        if s.num < current:
            parts.append(
                f'<a class="{cls} clickable" href="{_step_href(s.num)}" '
                f'target="_self" aria-label="Zu Schritt {s.num}: {s.title} springen">'
                f"{inner}</a>"
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


def _step_href(step: int) -> str:
    params = {
        key: st.query_params.get(key)
        for key in st.query_params
    }
    params["step"] = str(step)
    return "?" + urlencode(params, doseq=True)


# ---------- nav buttons ----------------------------------------------------

def render_step_nav(
    *,
    can_advance: bool = True,
    advance_disabled_reason: str = "",
    forward_label: str = "Weiter →",
    on_finish: Callable[[], None] | None = None,
    finish_label: str = "✓ Workflow abschließen",
) -> None:
    """Bottom navigation bar inside a step.

    - On step 1: only the forward button (default ``"Weiter →"``).
    - On step 2: both buttons.
    - On step 3: ``← Zurück`` + optional ``finish`` action.

    Pass ``forward_label`` to use a step-specific primary action like
    ``"✓ Positionen bestätigen"`` so the user always sees the named task
    instead of a generic "Weiter".
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
    """Always-available reset button that re-runs the pipeline.

    The actual API call lives in the caller — this widget just handles
    the confirmation dance and dispatches.
    """
    state_key = f"_reset_confirm_{review_id}"
    pending = st.session_state.get(state_key, False)

    if not confirm:
        if st.button(
            "🔄 Pipeline neu starten",
            key=f"_reset_{review_id}",
            use_container_width=True,
            help="Verarbeitet die Mail komplett neu mit der KI-Pipeline.",
        ):
            on_confirmed()
        return

    if not pending:
        if st.button(
            "🔄 Pipeline neu starten",
            key=f"_reset_{review_id}",
            use_container_width=True,
            help="Verarbeitet die Mail komplett neu mit der KI-Pipeline.",
        ):
            st.session_state[state_key] = True
            st.rerun()
        return

    st.warning(
        "Alle bisherigen Anpassungen werden verworfen und die Pipeline "
        "läuft komplett neu. Anhänge bleiben erhalten.",
        icon="⚠️",
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
