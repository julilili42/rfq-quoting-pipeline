from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from quoting.core import Anfrage
from quoting.output import build_draft_pdf
from quoting.pricing import build_quotation
from quoting.ui.review_agent import apply_manual_overrides, build_agent_summary
from quoting.ui.review_ui.resources import settings
from quoting.ui.review_ui.state import safe_file_stub


def pdf_output_path(content_hash: str) -> Path:
    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)

    return upload_dir / "draft_angebot.pdf"


def rebuild_quotation_pdf(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    agent_lang: str,
):
    base_quotation = build_quotation(
        anfrage,
        matches,
        settings().preise_path,
    )

    overrides = st.session_state.get("manual_discount_overrides", [])

    quotation, applied_items = apply_manual_overrides(
        base_quotation,
        anfrage,
        overrides,
        lang=agent_lang,
    )

    pdf_out = pdf_output_path(content_hash)

    build_draft_pdf(
        anfrage,
        quotation,
        pdf_out,
    )

    st.session_state["quotation"] = quotation
    st.session_state["quotation_hash"] = content_hash
    st.session_state["generated_pdf_path"] = str(pdf_out)
    st.session_state["pdf_bytes"] = pdf_out.read_bytes() if pdf_out.exists() else b""

    return quotation, applied_items, pdf_out


def render_generate_button(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    uploaded_name: str,
) -> None:
    if not st.button(
        "📝 Entwurf-Angebot erstellen",
        type="primary",
        use_container_width=True,
    ):
        return

    pdf_out = None

    with st.spinner("Erstelle PDF..."):
        try:
            agent_lang = st.session_state.get("agent_lang", "de")

            quotation, applied_items, pdf_out = rebuild_quotation_pdf(
                anfrage=anfrage,
                matches=matches,
                content_hash=content_hash,
                agent_lang=agent_lang,
            )

            if pdf_out.exists():
                st.session_state["pdf_file_name"] = (
                    f"ElringKlinger_Angebot_{safe_file_stub(uploaded_name)}_{content_hash}.pdf"
                )

                st.session_state["agent_messages"] = [
                    {
                        "role": "assistant",
                        "content": build_agent_summary(
                            quotation,
                            matches,
                            applied_items=applied_items,
                            lang=agent_lang,
                        ),
                    }
                ]

        except Exception as e:
            st.error(f"Fehler bei der Angebotserstellung: {e}")
            st.stop()

    if pdf_out and pdf_out.exists():
        st.success("✅ Angebot erfolgreich erstellt!")

        st.download_button(
            label="📥 Jetzt PDF herunterladen",
            data=st.session_state.get("pdf_bytes", b""),
            file_name=st.session_state.get(
                "pdf_file_name",
                f"ElringKlinger_Angebot_{content_hash}.pdf",
            ),
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        st.error("Fehler: PDF konnte nicht generiert werden. Prüfe, ob reportlab installiert ist.")