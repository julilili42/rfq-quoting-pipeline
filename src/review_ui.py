"""
Review-UI für Sales (Streamlit)
===============================
Starten mit: streamlit run src/review_ui.py

Zeigt Original-PDF + extrahierte Daten nebeneinander.
Sales kann Felder editieren, Matches bestätigen, dann Angebot finalisieren.
"""
from output import erstelle_draft_pdf
from pricing import berechne_quotation
from matching import lade_stammdaten, match_positionen
from extractor import Anfrage, Position
from pipeline import verarbeite_anfrage
from pathlib import Path
import json
import tempfile

import streamlit as st

st.set_page_config(
    page_title="Quotation Review",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ================================
# SIDEBAR: UPLOAD + KONFIG
# ================================

st.sidebar.title("🔧 Eingabe")
uploaded = st.sidebar.file_uploader(
    "Preisanfrage hochladen",
    type=["pdf", "eml", "xlsx", "xls"],
    help="PDF, E-Mail (.eml) oder Excel",
)
fuzzy_threshold = st.sidebar.slider(
    "Fuzzy-Match Schwelle", 50, 100, 85,
    help="Ab diesem Score gilt ein Fuzzy-Match als valide",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "### Ablauf\n"
    "1. Datei hochladen\n"
    "2. Extraktion prüfen\n"
    "3. Matches bestätigen\n"
    "4. Angebot erstellen"
)


# ================================
# MAIN: PIPELINE + REVIEW
# ================================

st.title("📋 Angebots-Entwurf — Review")

if not uploaded:
    st.info("⬅️ Links eine Preisanfrage hochladen, um zu starten.")
    st.stop()

# Temp-Datei schreiben
temp_dir = Path(tempfile.mkdtemp(prefix="quote_ui_"))
input_path = temp_dir / uploaded.name
input_path.write_bytes(uploaded.getvalue())

# Pipeline-Extraktion (cached pro Upload)


@st.cache_data(show_spinner="🤖 Extrahiere Daten aus dem Dokument...")
def _extrahiere(pfad_str: str) -> dict:
    from extractor import extrahiere_anfrage
    from ingestion import parse_mail, erkenne_dateityp

    p = Path(pfad_str)
    typ = erkenne_dateityp(p)
    if typ == "eml":
        mail = parse_mail(p)
        anfrage = extrahiere_anfrage(mail["attachments"], mail["body"])
    else:
        anfrage = extrahiere_anfrage([p], "")
    return anfrage.model_dump(mode="json")


try:
    anfrage_dict = _extrahiere(str(input_path))
    anfrage = Anfrage.model_validate(anfrage_dict)
except Exception as e:
    st.error(f"❌ Extraktion fehlgeschlagen: {e}")
    st.stop()

# ================================
# SPLIT VIEW: ORIGINAL + EXTRAKTION
# ================================

col_doc, col_extract = st.columns([1, 1])

with col_doc:
    st.subheader("📄 Original-Anfrage")
    if input_path.suffix.lower() == ".pdf":
        # PDF embedded
        import base64
        pdf_b64 = base64.b64encode(input_path.read_bytes()).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
            f'width="100%" height="800"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.info(f"Vorschau für {input_path.suffix} nicht verfügbar.")

with col_extract:
    st.subheader("🤖 Extrahierte Daten")

    # Header-Daten
    with st.expander("📌 Header & Kunde", expanded=True):
        anfrage.kunde_firma = st.text_input(
            "Kunde", anfrage.kunde_firma or "")
        anfrage.kunde_ansprechpartner = st.text_input(
            "Ansprechpartner", anfrage.kunde_ansprechpartner or "")
        anfrage.kunde_email = st.text_input(
            "E-Mail", anfrage.kunde_email or "")
        anfrage.belegnummer = st.text_input(
            "Kunden-Belegnummer", anfrage.belegnummer or "")
        anfrage.incoterms = st.text_input(
            "Incoterms", anfrage.incoterms or "")
        anfrage.zahlungsbedingungen = st.text_input(
            "Zahlungsbedingungen", anfrage.zahlungsbedingungen or "")

    # Positionen (editierbar)
    st.markdown("### Positionen")

    stammdaten = lade_stammdaten(
        Path(__file__).parent.parent / "data" / "stammdaten_test.csv")

    bearbeitete_positionen: list[Position] = []
    for i, pos in enumerate(anfrage.positionen):
        icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}[pos.confidence]
        label = (f"{icon} Pos {pos.pos_nr} — {pos.artikelnummer} "
                 f"({pos.menge:.0f} {pos.einheit})")

        with st.expander(label, expanded=(pos.confidence != "high")):
            c1, c2 = st.columns(2)
            with c1:
                pos.artikelnummer = st.text_input(
                    "Artikelnummer", pos.artikelnummer, key=f"art_{i}")
                pos.menge = st.number_input(
                    "Menge", value=float(pos.menge), key=f"mng_{i}")
                pos.einheit = st.text_input(
                    "Einheit", pos.einheit, key=f"eh_{i}")
            with c2:
                pos.liefertermin = st.text_input(
                    "Liefertermin", pos.liefertermin or "", key=f"lt_{i}")
                pos.werkstoff = st.text_input(
                    "Werkstoff", pos.werkstoff or "", key=f"ws_{i}")
                pos.zeichnungsnummer = st.text_input(
                    "Zeichnungs-Nr.", pos.zeichnungsnummer or "", key=f"zn_{i}")

            pos.bezeichnung = st.text_area(
                "Bezeichnung", pos.bezeichnung, key=f"bez_{i}", height=80)

            if pos.werkstoff_alternativen:
                st.caption(
                    f"Alternativen: {', '.join(pos.werkstoff_alternativen)}")
            if pos.ist_zertifikat:
                st.info("ℹ️ Diese Position ist ein Prüfzeugnis (keine Ware)")

            st.caption(f"🔍 Quelle: _{pos.source_quote}_")

            bearbeitete_positionen.append(pos)

    anfrage.positionen = bearbeitete_positionen

# ================================
# MATCHING + ANGEBOTS-BUTTON
# ================================

st.markdown("---")
st.subheader("🔗 Stammdaten-Abgleich")

matches = match_positionen(
    anfrage.positionen, stammdaten, fuzzy_threshold=fuzzy_threshold)

match_cols = st.columns(len(anfrage.positionen) or 1)
for i, (pos, match) in enumerate(zip(anfrage.positionen, matches)):
    with match_cols[i]:
        st.metric(
            f"Pos {pos.pos_nr}",
            match["status"].upper(),
            f"Score {match['score']:.0%}",
        )
        if match["matched_bezeichnung"]:
            st.caption(match["matched_bezeichnung"][:60])

# Finalisieren
st.markdown("---")
if st.button("📝 Draft-Angebot erstellen", type="primary", use_container_width=True):
    with st.spinner("Erstelle Angebots-PDF..."):
        quotation = berechne_quotation(
            anfrage=anfrage, matches=matches,
            preise_pfad=Path(__file__).parent.parent / "data" / "preise.csv",
        )
        pdf_out = temp_dir / "draft_angebot.pdf"
        erstelle_draft_pdf(anfrage, matches, quotation, pdf_out)

    st.success(
        f"✅ Angebot erstellt — Gesamt: {quotation['gesamtsumme']:,.2f} EUR")

    with open(pdf_out, "rb") as f:
        st.download_button(
            "📥 Draft-Angebot herunterladen",
            data=f.read(),
            file_name=f"Angebot_Draft_{anfrage.belegnummer or 'neu'}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if quotation["warnungen"]:
        st.warning("Prüfhinweise:\n- " + "\n- ".join(quotation["warnungen"]))

    with st.expander("📊 JSON-Export (Audit)"):
        st.json(quotation)
