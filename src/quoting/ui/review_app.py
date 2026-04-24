"""Streamlit review UI.

Launch (from project root):
streamlit run run_ui.py

Shows original document + extracted data side-by-side. Sales edits
fields, confirms matches, then finalizes the quotation.
"""
from __future__ import annotations

# Support direct execution by Streamlit (which runs the file as a top-level
# script). Adding project root to sys.path lets absolute `quoting.*` imports
# resolve whether launched via run_ui.py or directly.
import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
# src/quoting/ui/review_app.py -> ui -> quoting -> src -> <root>
_PROJECT_ROOT = _THIS_FILE.parents[3]
_SRC_DIR = _THIS_FILE.parents[2]

for p in (_PROJECT_ROOT, _SRC_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import base64
import hashlib
import tempfile

import streamlit as st

from quoting.core import Anfrage, Position, load_settings
from quoting.extraction import extract_anfrage
from quoting.ingestion import detect_file_type, parse_mail
from quoting.matching import load_stammdaten, match_positions
from quoting.output import build_draft_pdf
from quoting.pricing import build_quotation


st.set_page_config(
    page_title="Quotation Review",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -------- cached helpers --------

@st.cache_resource
def _settings():
    return load_settings()


@st.cache_resource
def _stammdaten():
    return load_stammdaten(_settings().stammdaten_path)


@st.cache_data(show_spinner="🤖 Extracting data...")
def _extract_cached(content_hash: str, file_path: str, mail_body: str) -> dict:
    """Run expensive LLM extraction once per uploaded file content."""
    _ = content_hash  # part of Streamlit cache key

    p = Path(file_path)
    typ = detect_file_type(p)

    if typ == "eml":
        mail = parse_mail(p)
        anfrage = extract_anfrage(mail.attachments, mail.body, _settings())
    else:
        anfrage = extract_anfrage([p], mail_body, _settings())

    return anfrage.model_dump(mode="json")


# -------- session-state helpers --------

_EDITOR_KEY_PREFIXES = (
    "art_",
    "mng_",
    "eh_",
    "lt_",
    "ws_",
    "zn_",
    "bez_",
)


def _reset_editor_state() -> None:
    """Remove old widget values when a new file is uploaded."""
    for key in list(st.session_state.keys()):
        if key.startswith(_EDITOR_KEY_PREFIXES):
            del st.session_state[key]


def _save_upload_stable(uploaded, content_hash: str) -> Path:
    """Save uploaded file to a stable path.

    Important:
    Do not use tempfile.mkdtemp() directly on every rerun for the input path,
    otherwise Streamlit sees a new file_path and may invalidate cache.
    """
    upload_dir = Path(tempfile.gettempdir()) / "quoting_streamlit_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)

    input_path = upload_dir / Path(uploaded.name).name

    if not input_path.exists():
        input_path.write_bytes(uploaded.getvalue())

    return input_path


def _load_anfrage_once(content_hash: str, input_path: Path, mail_body: str = "") -> Anfrage:
    """Load Anfrage only once per uploaded file content.

    - Same content_hash: reuse st.session_state["anfrage"]
    - New content_hash: run cached extraction once and reset editor widgets
    """
    cached_hash = st.session_state.get("anfrage_hash")

    if cached_hash != content_hash:
        _reset_editor_state()

        anfrage_dict = _extract_cached(content_hash, str(input_path), mail_body)
        st.session_state["anfrage"] = Anfrage.model_validate(anfrage_dict)
        st.session_state["anfrage_hash"] = content_hash

    return st.session_state["anfrage"]


# -------- sidebar --------

st.sidebar.title("🔧 Eingabe")

uploaded = st.sidebar.file_uploader(
    "Preisanfrage hochladen",
    type=["pdf", "eml", "xlsx", "xls"],
    help="PDF, Mail (.eml), or Excel",
)

fuzzy_threshold = st.sidebar.slider(
    "Fuzzy-Match threshold",
    50,
    100,
    85,
    help="Minimum score for a fuzzy match to count",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "### Workflow\n"
    "1. Upload file\n"
    "2. Check extraction\n"
    "3. Confirm matches\n"
    "4. Generate quotation"
)


# -------- main --------

st.title("📋 Angebots-Entwurf — Review")

if not uploaded:
    st.info("⬅️ Upload an RFQ on the left to start.")
    st.stop()


payload = uploaded.getvalue()
content_hash = hashlib.sha256(payload).hexdigest()[:16]
input_path = _save_upload_stable(uploaded, content_hash)

try:
    anfrage = _load_anfrage_once(content_hash, input_path, "")
except Exception as e:
    st.error(f"❌ Extraction failed: {e}")
    st.stop()


# -------- split view --------

col_doc, col_extract = st.columns([1, 1])

with col_doc:
    st.subheader("📄 Original-Anfrage")

    if input_path.suffix.lower() == ".pdf":
        pdf_b64 = base64.b64encode(payload).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
            f'width="100%" height="800"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.info(f"Preview for {input_path.suffix} not available.")


with col_extract:
    st.subheader("🤖 Extrahierte Daten")

    with st.expander("📌 Header & Kunde", expanded=True):
        anfrage.kunde_firma = st.text_input(
            "Kunde",
            anfrage.kunde_firma or "",
            key="kunde_firma",
        )
        anfrage.kunde_ansprechpartner = st.text_input(
            "Ansprechpartner",
            anfrage.kunde_ansprechpartner or "",
            key="kunde_ansprechpartner",
        )
        anfrage.kunde_email = st.text_input(
            "E-Mail",
            anfrage.kunde_email or "",
            key="kunde_email",
        )
        anfrage.belegnummer = st.text_input(
            "Kunden-Belegnummer",
            anfrage.belegnummer or "",
            key="belegnummer",
        )
        anfrage.incoterms = st.text_input(
            "Incoterms",
            anfrage.incoterms or "",
            key="incoterms",
        )
        anfrage.zahlungsbedingungen = st.text_input(
            "Zahlungsbedingungen",
            anfrage.zahlungsbedingungen or "",
            key="zahlungsbedingungen",
        )

    st.markdown("### Positionen")

    icons = {"high": "🟢", "medium": "🟡", "low": "🔴"}
    edited: list[Position] = []

    for i, pos in enumerate(anfrage.positionen):
        label = (
            f"{icons[pos.confidence]} Pos {pos.pos_nr} — "
            f"{pos.artikelnummer} ({pos.menge:.0f} {pos.einheit})"
        )

        with st.expander(label, expanded=(pos.confidence != "high")):
            c1, c2 = st.columns(2)

            with c1:
                pos.artikelnummer = st.text_input(
                    "Artikel-Nr.",
                    pos.artikelnummer,
                    key=f"art_{i}",
                )
                pos.menge = st.number_input(
                    "Menge",
                    value=float(pos.menge),
                    key=f"mng_{i}",
                )
                pos.einheit = st.text_input(
                    "Einheit",
                    pos.einheit,
                    key=f"eh_{i}",
                )

            with c2:
                pos.liefertermin = st.text_input(
                    "Liefertermin",
                    pos.liefertermin or "",
                    key=f"lt_{i}",
                )
                pos.werkstoff = st.text_input(
                    "Werkstoff",
                    pos.werkstoff or "",
                    key=f"ws_{i}",
                )
                pos.zeichnungsnummer = st.text_input(
                    "Zeichnungs-Nr.",
                    pos.zeichnungsnummer or "",
                    key=f"zn_{i}",
                )

            pos.bezeichnung = st.text_area(
                "Bezeichnung",
                pos.bezeichnung,
                key=f"bez_{i}",
                height=80,
            )

            if pos.werkstoff_alternativen:
                st.caption(f"Alternatives: {', '.join(pos.werkstoff_alternativen)}")

            if pos.ist_zertifikat:
                st.info("ℹ️ Certificate position (flat surcharge, no volume discount)")

            st.caption(f"🔍 Source: _{pos.source_quote}_")

        edited.append(pos)

    anfrage.positionen = edited
    st.session_state["anfrage"] = anfrage


# -------- matching --------

st.markdown("---")
st.subheader("🔗 Stammdaten-Abgleich")

matches = match_positions(
    anfrage.positionen,
    _stammdaten(),
    fuzzy_threshold=fuzzy_threshold,
    semantic_threshold=_settings().semantic_threshold,
)

cols = st.columns(max(len(anfrage.positionen), 1))

for i, (pos, m) in enumerate(zip(anfrage.positionen, matches)):
    with cols[i]:
        st.metric(
            f"Pos {pos.pos_nr}",
            m.status.upper(),
            f"Score {m.score:.0%}",
        )

        if m.matched_bezeichnung:
            st.caption(m.matched_bezeichnung[:60])


# -------- finalize --------

st.markdown("---")

if st.button("📝 Draft-Angebot erstellen", type="primary", use_container_width=True):
    with st.spinner("Building quotation PDF..."):
        quotation = build_quotation(anfrage, matches, _settings().preise_path)

        pdf_out = input_path.parent / "draft_angebot.pdf"
        build_draft_pdf(anfrage, quotation, pdf_out)

    st.success(f"✅ Created — Total: {quotation.gesamtsumme:,.2f} EUR")

    with open(pdf_out, "rb") as f:
        st.download_button(
            "📥 Download draft quotation",
            data=f.read(),
            file_name=f"Angebot_Draft_{anfrage.belegnummer or 'neu'}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if quotation.warnungen:
        st.warning("Review notes:\n- " + "\n- ".join(quotation.warnungen))

    with st.expander("📊 JSON export (audit)"):
        st.json(quotation.to_dict())