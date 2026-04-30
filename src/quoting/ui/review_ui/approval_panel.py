"""Simplified approval panel.

Two visible states only:

    Entwurf  →  Freigegeben

The underlying ``approval_store`` state machine is preserved (the API
and Outlook plugin still rely on it), but the UI exposes a single
action: enter your name, click *Freigeben*. That triggers a final-PDF
re-render without the red AI-warning banner. *Zurücknehmen* reverts to
the draft state.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.api.approval_store import (
    ApprovalRecord,
    load_approval,
    transition,
)


def render_approval_panel(
    review_dir: Path,
    on_finalize_pdf,
) -> ApprovalRecord:
    """Render the approval workflow."""
    record = load_approval(review_dir)

    is_approved = record.state in ("approved", "ready_to_send")

    if is_approved:
        _render_approved(review_dir, record)
    else:
        _render_pending(review_dir, on_finalize_pdf)

    return record


# --------------------------------------------------------------- pending

def _render_pending(review_dir: Path, on_finalize_pdf) -> None:
    st.info(
        "Der Angebotsentwurf enthält noch den roten KI-Warnhinweis. "
        "Mit der Freigabe wird das PDF ohne Warnhinweis neu erzeugt.",
    )

    actor = st.text_input(
        "Freigegeben durch",
        value=st.session_state.get("approval_actor", ""),
        placeholder="Vor- und Nachname",
        key="approval_actor_input",
    )
    st.session_state["approval_actor"] = actor

    can_approve = bool(actor.strip())
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        clicked = st.button(
            "Freigeben",
            type="primary",
            disabled=not can_approve,
            use_container_width=True,
            key="approval_approve",
            help=(
                "Bitte zuerst Namen eintragen."
                if not can_approve
                else "Erzeugt ein finales PDF ohne KI-Warnhinweis."
            ),
        )

    if not clicked:
        return

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
        changed_fields=sorted(st.session_state.get("changed_fields") or []),
    )
    st.success("Angebot freigegeben. Das finale PDF wurde erzeugt.")
    st.rerun()


# --------------------------------------------------------------- approved

def _render_approved(review_dir: Path, record: ApprovalRecord) -> None:
    actor = record.approved_by or "—"
    when = _short_iso(record.approved_at)
    final = record.final_pdf_path or "Angebot.pdf"

    st.success(
        f"Freigegeben durch **{actor}** am **{when}**.  \n"
        f"Finales PDF (ohne KI-Warnhinweis): `{final}`",
    )

    col_undo, _ = st.columns([1, 2])
    with col_undo:
        if st.button(
            "Freigabe zurücknehmen",
            use_container_width=True,
            key="approval_undo",
            help="Zurück in den Entwurfsmodus, der rote Warnhinweis "
                 "erscheint im PDF wieder.",
        ):
            transition(
                review_dir,
                target="reviewed",
                actor=record.approved_by,
            )
            st.rerun()


# --------------------------------------------------------------- helpers

def _short_iso(value: str | None) -> str:
    if not value:
        return "—"
    return value.split(".")[0].replace("T", " ")
