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
    if st.session_state.get("quotation_hash") != content_hash:
        return

    if not st.session_state.get("quotation"):
        return

    st.markdown("---")
    st.subheader("💬 Agent Chat")

    agent_lang = st.session_state.get("agent_lang", "de")
    messages = st.session_state.setdefault("agent_messages", [])

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    chat_placeholder = (
        "Write an edit: discount by position/article, comment, or total question"
        if agent_lang == "en"
        else "Schreibe eine Anpassung: Rabatt je Position/Artikel, Kommentar oder Summenfrage"
    )

    user_msg = st.chat_input(chat_placeholder)

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
            label="📥 PDF herunterladen nach dem Korrigieren",
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
    messages.append(
        {
            "role": "user",
            "content": user_msg,
        }
    )

    current_quotation = st.session_state["quotation"]

    known_articles = [
        p.artikelnummer
        for p in anfrage.positionen
        if p.artikelnummer
    ]

    parsed_override, parse_feedback = parse_edit_instruction(
        user_msg,
        known_articles,
        lang=agent_lang,
    )

    if parsed_override:
        overrides = st.session_state.get("manual_discount_overrides", [])

        st.session_state["manual_discount_overrides"] = upsert_override(
            overrides,
            parsed_override,
        )

        spinner_text = (
            "Applying edit and recalculating PDF..."
            if agent_lang == "en"
            else "Anpassung wird angewendet und PDF neu berechnet..."
        )

        with st.spinner(spinner_text):
            try:
                quotation, applied_items, _pdf_out = rebuild_quotation_pdf(
                    anfrage=anfrage,
                    matches=matches,
                    content_hash=content_hash,
                    agent_lang=agent_lang,
                )

            except Exception as e:
                messages.append(
                    {
                        "role": "assistant",
                        "content": (
                            f"Could not apply edit: {e}"
                            if agent_lang == "en"
                            else f"Anpassung konnte nicht angewendet werden: {e}"
                        ),
                    }
                )
                st.rerun()

        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"{parse_feedback}\n\n"
                    + build_agent_summary(
                        quotation,
                        matches,
                        applied_items=applied_items,
                        lang=agent_lang,
                    )
                ),
            }
        )

        st.rerun()

    if parse_feedback:
        messages.append(
            {
                "role": "assistant",
                "content": parse_feedback,
            }
        )
        st.rerun()

    messages.append(
        {
            "role": "assistant",
            "content": build_general_agent_reply(
                user_msg,
                current_quotation,
                lang=agent_lang,
            ),
        }
    )

    st.rerun()