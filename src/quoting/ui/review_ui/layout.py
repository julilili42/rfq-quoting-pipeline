from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def img_to_base64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


def apply_style() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');

            html, body, [data-testid="stAppViewContainer"] {
                font-family: 'Inter', sans-serif;
                background-color: #fcfcfc;
            }

            .header-container {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 50px;
                padding: 30px 20px;
                background: white;
                border-bottom: 1px solid #eee;
                margin-bottom: 40px;
            }

            .support-label {
                font-size: 13px;
                font-weight: 700;
                color: #adb5bd;
                text-transform: uppercase;
                letter-spacing: 2px;
            }

            .partner-logo {
                height: 80px;
                width: auto;
                object-fit: contain;
            }

            [data-testid="stSidebar"] {
                background-color: #ffffff !important;
            }

            .stButton>button {
                border-radius: 10px;
                font-weight: bold;
                padding: 0.75rem 2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st_logo = img_to_base64(ASSETS_DIR / "logo_bw_stiftung.png")
    wp_logo = img_to_base64(ASSETS_DIR / "logo_bw_wappen.png")
    bw_bank_logo = img_to_base64(ASSETS_DIR / "logo_bw_bank.png")

    header_html = '<div class="header-container"><span class="support-label">Unterstützt durch</span>'

    if st_logo:
        header_html += f'<img src="data:image/png;base64,{st_logo}" class="partner-logo">'

    if wp_logo:
        header_html += f'<img src="data:image/png;base64,{wp_logo}" class="partner-logo">'

    if bw_bank_logo:
        header_html += f'<img src="data:image/png;base64,{bw_bank_logo}" class="partner-logo">'

    header_html += "</div>"

    st.markdown(header_html, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        elring_logo = img_to_base64(ASSETS_DIR / "logo_elringklinger.png")

        if elring_logo:
            st.markdown(
                f'<img src="data:image/png;base64,{elring_logo}" '
                f'style="width: 100%; margin-bottom: 20px;">',
                unsafe_allow_html=True,
            )
        else:
            st.title("ElringKlinger")

        st.markdown("### 📥 Dateiupload")

        uploaded = st.file_uploader(
            "Anfrage hochladen",
            type=["pdf", "msg", "eml", "xlsx", "xls"],
            label_visibility="collapsed",
        )

        st.markdown("---")

        fuzzy_threshold = st.slider(
            "Fuzzy-Match Schwellenwert",
            min_value=50,
            max_value=100,
            value=85,
        )

        st.info(
            "💡 **Workflow:**\n"
            "1. Datei hochladen\n"
            "2. Daten prüfen\n"
            "3. Match bestätigen\n"
            "4. Angebot generieren"
        )

    return uploaded, fuzzy_threshold