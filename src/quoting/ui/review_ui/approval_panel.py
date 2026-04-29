"""Approval workflow panel.

Lives in step 3 (Versand). Renders the current approval state, lets the
user transition through the state machine, and triggers a final-PDF
re-render when the review is approved.

States are stored on disk via ``approval_store``; this module is the
view layer.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.api.approval_store import (
    ApprovalRecord,
    load_approval,
    save_approval,
    transition,
)


_STATE_META = {
    "draft_generated": {
        "label": "Entwurf bereit",
        "icon": "📝",
        "tone": "info",
        "description": "Pipeline hat einen ersten Entwurf erzeugt. Bitte prüfen.",
    },
    "reviewed": {
        "label": "Geprüft",
        "icon": "👁️",
        "tone": "info",
        "description": "Der Entwurf wurde inhaltlich gesichtet — bereit zur Freigabe.",
    },
    "approved": {
        "label": "Freigegeben",
        "icon": "✓",
        "tone": "success",
        "description": "Angebot freigegeben. Final-PDF ohne KI-Warnhinweis ist generiert.",
    },
    "ready_to_send": {
        "label": "Versandbereit",
        "icon": "📤",
        "tone": "success",
        "description": "PDF ist final und kann aus Outlook versendet werden.",
    },
}


def render_approval_panel(
    review_dir: Path,
    on_finalize_pdf,
) -> ApprovalRecord:
    """Render the approval workflow.

    Parameters
    ----------
    review_dir
        Folder where the approval record + final PDF live.
    on_finalize_pdf
        Callback invoked when the user transitions to ``approved``. It
        should regenerate the PDF without the red AI warning and return
        the relative filename.

    Returns
    -------
    The current ApprovalRecord.
    """
    record = load_approval(review_dir)

    _render_state_strip(record)

    st.markdown("&nbsp;", unsafe_allow_html=True)
    _render_actions(review_dir, record, on_finalize_pdf)

    if record.changed_fields:
        with st.expander(
            f"📋 Geänderte Felder ({len(record.changed_fields)})",
            expanded=False,
        ):
            for path in record.changed_fields:
                st.markdown(f"- `{path}`")

    if record.history:
        with st.expander("🕓 Verlauf", expanded=False):
            for entry in reversed(record.history[-10:]):
                actor = entry.get("actor") or "—"
                st.markdown(
                    f"**{entry.get('at', '?')}** · "
                    f"`{entry.get('from', '?')}` → `{entry.get('to', '?')}` "
                    f"· {actor}"
                )

    return record


def _render_state_strip(record: ApprovalRecord) -> None:
    """Visual progress strip showing the four-stage approval flow."""
    states_order = ["draft_generated", "reviewed", "approved", "ready_to_send"]
    current_idx = states_order.index(record.state) if record.state in states_order else 0

    parts = ['<div class="ek-approval-strip">']
    for i, state in enumerate(states_order):
        meta = _STATE_META[state]
        if i < current_idx:
            cls = "done"
        elif i == current_idx:
            cls = "active"
        else:
            cls = "idle"
        parts.append(
            f'<div class="ek-approval-step ek-approval-{cls}">'
            f'  <div class="ek-approval-icon">{meta["icon"]}</div>'
            f'  <div class="ek-approval-label">{meta["label"]}</div>'
            f'</div>'
        )
        if i < len(states_order) - 1:
            sep_cls = "done" if i < current_idx else "idle"
            parts.append(f'<div class="ek-approval-sep ek-approval-sep-{sep_cls}"></div>')
    parts.append("</div>")

    st.markdown("".join(parts), unsafe_allow_html=True)

    # Description of current state
    meta = _STATE_META.get(record.state, _STATE_META["draft_generated"])
    icon_class = {
        "info": "ek-state-info",
        "success": "ek-state-success",
        "warning": "ek-state-warning",
    }.get(meta["tone"], "ek-state-info")
    st.markdown(
        f"""
        <div class="ek-state-card {icon_class}">
          <div class="ek-state-card-head">
            <span class="ek-state-icon-large">{meta['icon']}</span>
            <span class="ek-state-card-title">{meta['label']}</span>
          </div>
          <div class="ek-state-card-desc">{meta['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Detail line
    if record.approved_by and record.state in ("approved", "ready_to_send"):
        st.caption(
            f"Freigegeben von **{record.approved_by}** am "
            f"{_short_iso(record.approved_at)}"
        )


def _render_actions(
    review_dir: Path,
    record: ApprovalRecord,
    on_finalize_pdf,
) -> None:
    """Action buttons that drive the state machine."""
    state = record.state

    if state == "draft_generated":
        _render_review_action(review_dir, record)
    elif state == "reviewed":
        _render_approve_action(review_dir, on_finalize_pdf)
    elif state == "approved":
        _render_send_action(review_dir, record)
    elif state == "ready_to_send":
        _render_resend_action(review_dir, record)


def _render_review_action(review_dir: Path, record: ApprovalRecord) -> None:
    st.warning(
        "Das PDF enthält noch den **roten KI-Warnhinweis**. "
        "Markiere als geprüft sobald du den Inhalt validiert hast.",
        icon="⚠️",
    )
    col1, _ = st.columns([1, 2])
    with col1:
        if st.button(
            "👁️ Als geprüft markieren",
            type="primary",
            use_container_width=True,
            key="approval_mark_reviewed",
        ):
            actor = _ask_actor()
            transition(
                review_dir,
                target="reviewed",
                actor=actor,
                changed_fields=sorted(st.session_state.get("changed_fields") or []),
            )
            st.rerun()


def _render_approve_action(review_dir: Path, on_finalize_pdf) -> None:
    st.info(
        "Bitte den Warnhinweis bestätigen und freigeben — anschließend wird "
        "das PDF **ohne KI-Hinweis** neu generiert.",
        icon="ℹ️",
    )

    ack = st.checkbox(
        "Ich bestätige, dass ich den Inhalt geprüft habe und das Angebot freigeben will.",
        key="approval_ack",
    )

    actor = st.text_input(
        "Freigegeben durch",
        value=st.session_state.get("approval_actor", ""),
        placeholder="z. B. M. Mustermann",
        key="approval_actor_input",
    )
    st.session_state["approval_actor"] = actor

    col1, _ = st.columns([1, 2])
    with col1:
        if st.button(
            "✓ Final freigeben",
            type="primary",
            disabled=not (ack and actor.strip()),
            use_container_width=True,
            key="approval_approve",
            help="Erst Bestätigung & Name eintragen.",
        ):
            try:
                final_filename = on_finalize_pdf()
            except Exception as exc:
                st.error(f"Final-PDF konnte nicht erzeugt werden: {exc}")
                return
            transition(
                review_dir,
                target="approved",
                actor=actor.strip(),
                warning_acknowledged=True,
                final_pdf_path=final_filename,
            )
            st.success("Angebot freigegeben. Final-PDF wurde erzeugt.", icon="✅")
            st.rerun()


def _render_send_action(review_dir: Path, record: ApprovalRecord) -> None:
    st.success(
        f"Final-PDF ist bereit: **{record.final_pdf_path or 'Angebot.pdf'}**. "
        "Versand erfolgt aus Outlook.",
        icon="✅",
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "📤 Als versendet markieren",
            type="primary",
            use_container_width=True,
            key="approval_send",
        ):
            transition(
                review_dir,
                target="ready_to_send",
                actor=record.approved_by,
            )
            st.rerun()
    with col2:
        if st.button(
            "↩️ Freigabe zurücknehmen",
            use_container_width=True,
            key="approval_unapprove",
        ):
            transition(
                review_dir,
                target="reviewed",
                actor=record.approved_by,
            )
            st.rerun()


def _render_resend_action(review_dir: Path, record: ApprovalRecord) -> None:
    st.success(
        f"Versendet am **{_short_iso(record.sent_at)}**. "
        "Workflow abgeschlossen.",
        icon="✅",
    )


def _ask_actor() -> str:
    """Best-effort: pull a 'who is this' value from session state."""
    return st.session_state.get("approval_actor", "Unknown")


def _short_iso(value: str | None) -> str:
    if not value:
        return "—"
    # Trim microseconds + timezone for compact display.
    return value.split(".")[0].replace("T", " ")
