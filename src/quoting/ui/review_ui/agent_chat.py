"""Agent chat panel — natural-language commercial edits on the quotation.

Layout note: the chat input is rendered at the *top* of the panel (just
under the section label), so it never sits awkwardly below the
workflow-completion buttons. The conversation history and the latest
download button render below the input.

Icon policy: no decorative emoji on labels, callouts, or downloads. The
rest of the app is intentionally quiet, the chat panel follows suit.
"""
from __future__ import annotations

import streamlit as st

from quoting.core import Anfrage
from quoting.ui.review_agent import (
    build_agent_summary,
    build_general_agent_reply,
    parse_edit_instruction,
    upsert_override,
)
from quoting.ui.review_ui.quotation_flow import rebuild_quotation_pdf


def render_agent_chat(
    anfrage: Anfrage,
    matches,
    content_hash: str,
) -> None:
    """Render the agent chat. Requires a generated quotation in state."""
    if st.session_state.get("quotation_hash") != content_hash:
        return
    if not st.session_state.get("quotation"):
        return

    st.markdown(
        '<div class="ek-section-label">Agent-Chat · Anpassungen in Klartext</div>',
        unsafe_allow_html=True,
    )

    agent_lang = st.session_state.get("agent_lang", "de")

    chat_placeholder = (
        "Schreibe eine Anpassung: Rabatt je Position/Artikel, Kommentar oder Summenfrage"
        if agent_lang == "de"
        else "Write an edit: discount by position/article, comment, or total question"
    )
    user_msg = st.chat_input(chat_placeholder)

    messages = st.session_state.setdefault("agent_messages", [])

    if not messages:
        intro = (
            "Try: *Discount 5% on article ABC*, *Set pos 3 to 12 EUR*, "
            "*What is the total?*"
            if agent_lang == "en"
            else "Beispiele: *5% Rabatt auf Artikel ABC*, *Setze pos 3 auf 12 EUR*, "
                 "*Wie hoch ist die Summe?*"
        )
        st.info(intro)

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_msg:
        _handle_agent_message(
            user_msg=user_msg,
            anfrage=anfrage,
            matches=matches,
            content_hash=content_hash,
            agent_lang=agent_lang,
            messages=messages,
        )

    if st.session_state.get("pdf_bytes"):
        st.download_button(
            label="Aktuelles PDF herunterladen",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state.get(
                "pdf_file_name",
                f"ElringKlinger_Angebot_{content_hash}.pdf",
            ),
            mime="application/pdf",
            use_container_width=True,
            key="download_after_chat",
        )


def _handle_agent_message(
    user_msg: str,
    anfrage: Anfrage,
    matches,
    content_hash: str,
    agent_lang: str,
    messages: list[dict],
) -> None:
    messages.append({"role": "user", "content": user_msg})

    current_quotation = st.session_state["quotation"]
    known_articles = [
        p.artikelnummer for p in anfrage.positionen if p.artikelnummer
    ]
    parsed_override, parse_feedback = parse_edit_instruction(
        user_msg, known_articles, lang=agent_lang
    )

    if parsed_override:
        overrides = st.session_state.get("manual_discount_overrides", [])
        st.session_state["manual_discount_overrides"] = upsert_override(
            overrides, parsed_override
        )
        spinner_text = (
            "Anpassung wird angewendet und PDF neu berechnet..."
            if agent_lang == "de"
            else "Applying edit and recalculating PDF..."
        )
        with st.spinner(spinner_text):
            try:
                quotation, applied_items, _pdf_out = rebuild_quotation_pdf(
                    anfrage=anfrage, matches=matches,
                    content_hash=content_hash, agent_lang=agent_lang,
                )
            except Exception as e:
                err = (
                    f"Anpassung konnte nicht angewendet werden: {e}"
                    if agent_lang == "de"
                    else f"Could not apply edit: {e}"
                )
                messages.append({"role": "assistant", "content": err})
                st.rerun()

        messages.append({
            "role": "assistant",
            "content": (
                f"{parse_feedback}\n\n"
                + build_agent_summary(
                    quotation, matches,
                    applied_items=applied_items, lang=agent_lang,
                )
            ),
        })
        st.rerun()

    if parse_feedback:
        messages.append({"role": "assistant", "content": parse_feedback})
        st.rerun()

    messages.append({
        "role": "assistant",
        "content": build_general_agent_reply(
            user_msg, current_quotation, lang=agent_lang
        ),
    })
    st.rerun()
