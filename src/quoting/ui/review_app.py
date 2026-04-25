"""
Streamlit Review UI - ElringKlinger Edition
Optimiertes Frontend mit Partner-Integration.
"""
from __future__ import annotations

import sys
import base64
import hashlib
import re
import tempfile
from pathlib import Path

import streamlit as st

# --- Pfad-Logik für interne Module ---
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
_SRC_DIR = _THIS_FILE.parents[2]

for p in (_PROJECT_ROOT, _SRC_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from quoting.core import Anfrage, Position, load_settings
from quoting.extraction import extract_anfrage
from quoting.ingestion import detect_file_type, parse_mail
from quoting.matching import load_stammdaten, match_positions
from quoting.output import build_draft_pdf
from quoting.pricing import build_quotation
from quoting.ui.review_agent import (
    apply_manual_overrides,
    build_agent_summary,
    build_general_agent_reply,
    detect_agent_language,
    parse_edit_instruction,
    upsert_override,
)

# ==========================================
# PAGE CONFIG & STYLING
# ==========================================
st.set_page_config(
    page_title="ElringKlinger | Quotation Review",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)
def apply_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
        
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', sans-serif;
            background-color: #fcfcfc;
        }

        /* HEADER LOGOS: DEUTLICH GRÖSSER */
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
            height: 80px; /* Hier: Von 35px auf 80px erhöht */
            width: auto;
            object-fit: contain;
        }

        /* Sidebar & Buttons */
        [data-testid="stSidebar"] { background-color: #ffffff !important; }
        .stButton>button {
            border-radius: 10px;
            font-weight: bold;
            padding: 0.75rem 2rem;
        }
        </style>
    """, unsafe_allow_html=True)

apply_style()

# --- Utility für Bilder ---
def img_to_base64(path):
    p = Path(path)
    if not p.exists(): return None
    return base64.b64encode(p.read_bytes()).decode()

# ==========================================
# CACHED HELPERS
# ==========================================
@st.cache_resource
def _settings():
    return load_settings()

@st.cache_resource
def _stammdaten():
    return load_stammdaten(_settings().stammdaten_path)

@st.cache_data(show_spinner="🤖 KI extrahiert Daten...")
def _extract_cached(content_hash: str, file_path: str, mail_body: str) -> dict:
    p = Path(file_path)
    typ = detect_file_type(p)
    if typ in ["eml", "msg"]:
        mail = parse_mail(p)
        anfrage = extract_anfrage(mail.attachments, mail.body, _settings())
    else:
        anfrage = extract_anfrage([p], mail_body, _settings())
    return anfrage.model_dump(mode="json")


@st.cache_data
def _mail_body_cached(file_path: str) -> str:
    p = Path(file_path)
    if detect_file_type(p) in ["eml", "msg"]:
        return parse_mail(p).body or ""
    return ""

# --- Session State Helpers ---
_EDITOR_KEY_PREFIXES = ("art_", "mng_", "eh_", "lt_", "ws_", "zn_", "bez_")


def _reset_agent_state() -> None:
    for key in (
        "manual_discount_overrides",
        "agent_messages",
        "quotation",
        "quotation_hash",
        "pdf_bytes",
        "pdf_file_name",
        "generated_pdf_path",
    ):
        if key in st.session_state:
            del st.session_state[key]

def _reset_editor_state():
    for key in list(st.session_state.keys()):
        if key.startswith(_EDITOR_KEY_PREFIXES):
            del st.session_state[key]

def _save_upload_stable(uploaded, content_hash: str) -> Path:
    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)
    input_path = upload_dir / Path(uploaded.name).name
    if not input_path.exists():
        input_path.write_bytes(uploaded.getvalue())
    return input_path

def _load_anfrage_once(content_hash: str, input_path: Path) -> Anfrage:
    if st.session_state.get("anfrage_hash") != content_hash:
        _reset_editor_state()
        _reset_agent_state()
        anfrage_dict = _extract_cached(content_hash, str(input_path), "")
        st.session_state["anfrage"] = Anfrage.model_validate(anfrage_dict)
        st.session_state["anfrage_hash"] = content_hash
    return st.session_state["anfrage"]


def _safe_file_stub(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "angebot"

# ==========================================
# UI HEADER (PARTNER LOGOS)
# ==========================================
st_logo = img_to_base64("./src/quoting/ui/assets/logo_bw_stiftung.png")
wp_logo = img_to_base64("./src/quoting/ui/assets/logo_bw_wappen.png")
bw_bank_logo = img_to_base64("./src/quoting/ui/assets/logo_bw_bank.png")

header_html = f'<div class="header-container"><span class="support-label">Unterstützt durch</span>'
if st_logo: header_html += f'<img src="data:image/png;base64,{st_logo}" class="partner-logo">'
if wp_logo: header_html += f'<img src="data:image/png;base64,{wp_logo}" class="partner-logo">'
if bw_bank_logo: header_html += f'<img src="data:image/png;base64,{bw_bank_logo}" class="partner-logo">'
header_html += '</div>'
st.markdown(header_html, unsafe_allow_html=True)

# ==========================================
# SIDEBAR (BRANDING & EINGABE)
# ==========================================
with st.sidebar:
    elring_logo = img_to_base64("./src/quoting/ui/assets/logo_elringklinger.png")
    if elring_logo:
        st.markdown(f'<img src="data:image/png;base64,{elring_logo}" style="width: 100%; margin-bottom: 20px;">', unsafe_allow_html=True)
    else:
        st.title("ElringKlinger")
    
    st.markdown("### 📥 Dateiupload")
    uploaded = st.file_uploader(
        "Anfrage hochladen",
        type=["pdf", "msg", "eml", "xlsx", "xls"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    fuzzy_threshold = st.slider("Fuzzy-Match Schwellenwert", 50, 100, 85)
    
    st.info("💡 **Workflow:**\n1. Datei hochladen\n2. Daten prüfen\n3. Match bestätigen\n4. Angebot generieren")

# ==========================================
# MAIN CONTENT
# ==========================================
st.markdown('<h1 class="main-header">📋 Angebots-Review</h1>', unsafe_allow_html=True)

if not uploaded:
    st.info("Bitte laden Sie links eine Preisanfrage hoch, um zu beginnen.")
    st.stop()

payload = uploaded.getvalue()
content_hash = hashlib.sha256(payload).hexdigest()[:16]
input_path = _save_upload_stable(uploaded, content_hash)

try:
    anfrage = _load_anfrage_once(content_hash, input_path)
except Exception as e:
    st.error(f"❌ Fehler bei der Extraktion: {e}")
    st.stop()

mail_body_for_lang = _mail_body_cached(str(input_path))
fallback_lang_text = " ".join(
    [
        anfrage.kunde_firma or "",
        anfrage.kunde_ansprechpartner or "",
        anfrage.belegnummer or "",
        " ".join((p.source_quote or "") for p in anfrage.positionen[:3]),
    ]
)
if st.session_state.get("agent_lang_hash") != content_hash:
    st.session_state["agent_lang"] = detect_agent_language(mail_body_for_lang, fallback_lang_text)
    st.session_state["agent_lang_hash"] = content_hash

# --- Split View ---
col_doc, col_extract = st.columns([1, 1], gap="large")

with col_doc:
    st.subheader("📄 Original-Anfrage")
    if input_path.suffix.lower() == ".pdf":
        pdf_b64 = base64.b64encode(payload).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
            f'width="100%" height="850px" style="border: none; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"Vorschau für {input_path.suffix} nicht verfügbar.")

with col_extract:
    st.subheader("🤖 Extrahierte Daten")
    
    with st.expander("🏢 Header & Kundeninformationen", expanded=True):
        c_k1, c_k2 = st.columns(2)
        anfrage.kunde_firma = c_k1.text_input("Firma", anfrage.kunde_firma or "")
        anfrage.kunde_ansprechpartner = c_k2.text_input("Ansprechpartner", anfrage.kunde_ansprechpartner or "")
        anfrage.kunde_email = c_k1.text_input("E-Mail", anfrage.kunde_email or "")
        anfrage.belegnummer = c_k2.text_input("Referenz-Nr", anfrage.belegnummer or "")

    st.markdown("#### Positionen")
    icons = {"high": "🟢", "medium": "🟡", "low": "🔴"}
    edited_positions = []

    for i, pos in enumerate(anfrage.positionen):
        status_icon = icons.get(pos.confidence, "⚪")
        label = f"{status_icon} Pos {pos.pos_nr} — {pos.artikelnummer or 'Unbekannt'}"
        
        with st.expander(label):
            c1, c2 = st.columns(2)
            with c1:
                pos.artikelnummer = st.text_input("Art-Nr.", pos.artikelnummer, key=f"art_{i}")
                pos.menge = st.number_input("Menge", value=float(pos.menge), key=f"mng_{i}")
                pos.einheit = st.text_input("Einheit", pos.einheit, key=f"eh_{i}")
            with c2:
                pos.liefertermin = st.text_input("Liefertermin", pos.liefertermin or "", key=f"lt_{i}")
                pos.werkstoff = st.text_input("Werkstoff", pos.werkstoff or "", key=f"ws_{i}")
                pos.zeichnungsnummer = st.text_input("Zeichnungs-Nr.", pos.zeichnungsnummer or "", key=f"zn_{i}")
            
            pos.bezeichnung = st.text_area("Bezeichnung", pos.bezeichnung, key=f"bez_{i}", height=70)
        edited_positions.append(pos)

    anfrage.positionen = edited_positions
    st.session_state["anfrage"] = anfrage

# --- Matching & Finalize ---
st.markdown("---")
st.subheader("🔗 Stammdaten-Abgleich")

matches = match_positions(
    anfrage.positionen, 
    _stammdaten(), 
    fuzzy_threshold=fuzzy_threshold,
    semantic_threshold=_settings().semantic_threshold
)

m_cols = st.columns(len(anfrage.positionen) if anfrage.positionen else 1)
for i, (pos, m) in enumerate(zip(anfrage.positionen, matches)):
    with m_cols[i]:
        color = "normal" if m.score > 0.8 else "inverse"
        st.metric(f"Pos {pos.pos_nr}", f"{m.score:.0%}", m.status.upper(), delta_color=color)

if st.button("📝 Entwurf-Angebot erstellen", type="primary", use_container_width=True):
    with st.spinner("Erstelle PDF..."):
        try:
            agent_lang = st.session_state.get("agent_lang", "de")
            base_quotation = build_quotation(anfrage, matches, _settings().preise_path)
            overrides = st.session_state.get("manual_discount_overrides", [])
            quotation, applied_items = apply_manual_overrides(base_quotation, anfrage, overrides, lang=agent_lang)

            upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
            upload_dir.mkdir(parents=True, exist_ok=True)
            pdf_out = upload_dir / "draft_angebot.pdf"

            build_draft_pdf(anfrage, quotation, pdf_out)

            if pdf_out.exists():
                st.session_state["quotation"] = quotation
                st.session_state["quotation_hash"] = content_hash
                st.session_state["generated_pdf_path"] = str(pdf_out)
                st.session_state["pdf_bytes"] = pdf_out.read_bytes()
                st.session_state["pdf_file_name"] = (
                    f"ElringKlinger_Angebot_{_safe_file_stub(uploaded.name)}_{content_hash}.pdf"
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

        if pdf_out.exists():
            st.success("✅ Angebot erfolgreich erstellt!")
            st.download_button(
                label="📥 Jetzt PDF herunterladen",
                data=st.session_state.get("pdf_bytes", b""),
                file_name=st.session_state.get("pdf_file_name", f"ElringKlinger_Angebot_{content_hash}.pdf"),
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.error("Fehler: PDF konnte nicht generiert werden. Prüfe, ob reportlab installiert ist.")

if st.session_state.get("quotation_hash") == content_hash and st.session_state.get("quotation"):
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
        messages.append({"role": "user", "content": user_msg})

        current_quotation = st.session_state["quotation"]
        known_articles = [p.artikelnummer for p in anfrage.positionen if p.artikelnummer]
        parsed_override, parse_feedback = parse_edit_instruction(
            user_msg,
            known_articles,
            lang=agent_lang,
        )

        if parsed_override:
            overrides = st.session_state.get("manual_discount_overrides", [])
            st.session_state["manual_discount_overrides"] = upsert_override(overrides, parsed_override)

            with st.spinner("Applying edit and recalculating PDF..." if agent_lang == "en" else "Anpassung wird angewendet und PDF neu berechnet..."):
                try:
                    base_quotation = build_quotation(anfrage, matches, _settings().preise_path)
                    quotation, applied_items = apply_manual_overrides(
                        base_quotation,
                        anfrage,
                        st.session_state.get("manual_discount_overrides", []),
                        lang=agent_lang,
                    )

                    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    pdf_out = upload_dir / "draft_angebot.pdf"
                    build_draft_pdf(anfrage, quotation, pdf_out)

                    st.session_state["quotation"] = quotation
                    st.session_state["quotation_hash"] = content_hash
                    st.session_state["generated_pdf_path"] = str(pdf_out)
                    st.session_state["pdf_bytes"] = pdf_out.read_bytes() if pdf_out.exists() else b""
                except Exception as e:
                    messages.append({
                        "role": "assistant",
                        "content": (f"Could not apply edit: {e}" if agent_lang == "en" else f"Anpassung konnte nicht angewendet werden: {e}"),
                    })
                    st.rerun()

            messages.append({
                "role": "assistant",
                "content": (
                    f"{parse_feedback}\n\n"
                    + build_agent_summary(
                        st.session_state["quotation"],
                        matches,
                        applied_items=applied_items,
                        lang=agent_lang,
                    )
                ),
            })
            st.rerun()

        if parse_feedback:
            messages.append({"role": "assistant", "content": parse_feedback})
            st.rerun()

        messages.append({
            "role": "assistant",
            "content": build_general_agent_reply(user_msg, current_quotation, lang=agent_lang),
        })
        st.rerun()

    if st.session_state.get("pdf_bytes"):
        st.download_button(
            label="📥 PDF herunterladen nach dem Korrigieren",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state.get("pdf_file_name", f"ElringKlinger_Angebot_{content_hash}.pdf"),
            mime="application/pdf",
            use_container_width=True,
            key="download_after_chat",
        )