from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


def render_original_request(input_path: Path, payload: bytes) -> None:
    st.subheader("📄 Original-Anfrage")

    if input_path.suffix.lower() == ".pdf":
        pdf_b64 = base64.b64encode(payload).decode()

        st.markdown(
            f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
            f'width="100%" '
            f'height="850px" '
            f'style="border: none; border-radius: 8px; '
            f'box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">'
            f"</iframe>",
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Vorschau für {input_path.suffix} nicht verfügbar.")