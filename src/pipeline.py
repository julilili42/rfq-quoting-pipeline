"""
ElringKlinger Quoting-Pipeline
==============================
End-to-End-Verarbeitung von Preisanfragen:
  Mail/PDF/Excel -> Extraktion -> Matching -> Berechnung -> Draft-Quotation

Architektur:
  1. Ingestion    - Mail + Attachments aufteilen
  2. Routing      - pro Input-Typ passender Extraktor
  3. Extraktion   - strukturierte Positionen via LLM (Pydantic-validiert)
  4. Matching     - Artikelnummer gegen Stammdaten
  5. Berechnung   - Preis inkl. Staffel + SAP ZKALK-Offset (Mock)
  6. Output       - JSON + Draft-PDF
"""
import os
import argparse
import time
import json
from pathlib import Path
from typing import Optional

from extractor import extrahiere_anfrage, Anfrage
from ingestion import parse_mail, erkenne_dateityp
from matching import match_positionen, lade_stammdaten
from pricing import berechne_quotation
from output import erstelle_draft_pdf, speichere_json

# ==============================
# KONFIGURATION
# ==============================
DEFAULT_OUTPUT_FOLDER = r"C:\Business & AI\Output"
STAMMDATEN_PFAD = Path(__file__).parent.parent / "data" / "stammdaten_test.csv"
PREISE_PFAD = Path(__file__).parent.parent / "data" / "preise.csv"


def verarbeite_anfrage(
    input_pfad: Path,
    ausgabe_ordner: Path,
    mail_body: str = "",
) -> dict:
    """
    Hauptfunktion: Nimmt eine Preisanfrage (PDF, EML oder Excel) entgegen
    und durchläuft die komplette Pipeline bis zum Draft-Angebot.

    Returns: Dict mit allen Zwischenergebnissen für Audit/Debug.
    """
    dateiname = input_pfad.name
    name = input_pfad.stem
    arbeits_ordner = ausgabe_ordner / name
    arbeits_ordner.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"📄 Verarbeite : {dateiname}")
    print(f"📂 Ausgabe    : {arbeits_ordner}")
    print(f"{'=' * 60}")

    ergebnisse = {"input": str(input_pfad)}

    # --- Schritt 1: Ingestion (je nach Input-Typ) ---
    typ = erkenne_dateityp(input_pfad)
    print(f"\n🔍 Erkannter Typ: {typ}")

    if typ == "eml":
        mail_data = parse_mail(input_pfad)
        mail_body = mail_data["body"]
        attachments = mail_data["attachments"]
        print(f"   📧 Mail-Body: {len(mail_body)} Zeichen")
        print(f"   📎 Attachments: {len(attachments)}")
    elif typ == "pdf":
        attachments = [input_pfad]
    elif typ in ("xlsx", "xls", "csv"):
        attachments = [input_pfad]
    else:
        raise ValueError(f"Unbekannter Input-Typ: {typ}")

    # --- Schritt 2 + 3: Extraktion ---
    print(f"\n🤖 Schritt 2+3: LLM-Extraktion der Positionen...")
    anfrage: Anfrage = extrahiere_anfrage(
        attachments=attachments,
        mail_body=mail_body,
    )
    print(f"   ✅ {len(anfrage.positionen)} Position(en) extrahiert")
    for pos in anfrage.positionen:
        confidence_icon = {"high": "🟢",
                           "medium": "🟡", "low": "🔴"}[pos.confidence]
        print(f"   {confidence_icon} Pos {pos.pos_nr}: {pos.artikelnummer} "
              f"({pos.menge} {pos.einheit}) - {pos.bezeichnung[:50]}")

    speichere_json(anfrage.model_dump(mode="json"),
                   arbeits_ordner / "01_extracted.json")
    ergebnisse["extraktion"] = anfrage.model_dump(mode="json")

    # --- Schritt 4: Matching gegen Stammdaten ---
    print(f"\n🔗 Schritt 4: Matching gegen Stammdaten...")
    stammdaten = lade_stammdaten(STAMMDATEN_PFAD)
    matches = match_positionen(anfrage.positionen, stammdaten)

    for pos, match in zip(anfrage.positionen, matches):
        status_icon = {"exact": "✅", "fuzzy": "⚠️ ",
                       "semantic": "🔍", "no_match": "❌"}[match["status"]]
        print(f"   {status_icon} Pos {pos.pos_nr}: {match['status']} "
              f"(Score: {match['score']:.2f})")

    speichere_json(matches, arbeits_ordner / "02_matches.json")
    ergebnisse["matches"] = matches

    # --- Schritt 5: Preisberechnung ---
    print(f"\n💰 Schritt 5: Preisberechnung...")
    quotation = berechne_quotation(
        anfrage=anfrage,
        matches=matches,
        preise_pfad=PREISE_PFAD,
    )
    gesamt = quotation["gesamtsumme"]
    print(f"   💵 Gesamtsumme: {gesamt:,.2f} EUR")

    speichere_json(quotation, arbeits_ordner / "03_quotation.json")
    ergebnisse["quotation"] = quotation

    # --- Schritt 6: Draft-PDF ---
    print(f"\n📝 Schritt 6: Draft-Angebot erstellen...")
    pdf_pfad = arbeits_ordner / f"{name}_ANGEBOT_DRAFT.pdf"
    erstelle_draft_pdf(anfrage, matches, quotation, pdf_pfad)
    print(f"   ✅ Draft-PDF: {pdf_pfad}")
    ergebnisse["draft_pdf"] = str(pdf_pfad)

    print(f"\n{'=' * 60}")
    print(f"✅ PIPELINE ABGESCHLOSSEN: {dateiname}")
    print(f"   📋 Positionen: {len(anfrage.positionen)}")
    print(
        f"   ✅ Exakte Matches: {sum(1 for m in matches if m['status'] == 'exact')}")
    print(f"   ⚠️  Fuzzy: {sum(1 for m in matches if m['status'] == 'fuzzy')}")
    print(
        f"   ❌ Keine Matches: {sum(1 for m in matches if m['status'] == 'no_match')}")
    print(f"   💵 Gesamtsumme: {gesamt:,.2f} EUR")
    print(f"{'=' * 60}")

    return ergebnisse


def parse_args():
    parser = argparse.ArgumentParser(
        description="ElringKlinger Quoting-Pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python -m src.pipeline request.pdf\n"
            "  python -m src.pipeline mail.eml --output C:\\Ergebnisse\n"
        )
    )
    parser.add_argument("input", metavar="INPUT",
                        help="Pfad zur Preisanfrage (PDF, EML, XLSX)")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_FOLDER,
                        help=f"Ausgabeordner (Standard: {DEFAULT_OUTPUT_FOLDER})")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start = time.time()

    input_pfad = Path(args.input)
    ausgabe_ordner = Path(args.output)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)

    if not input_pfad.exists():
        print(f"❌ Datei nicht gefunden: {input_pfad}")
    else:
        try:
            verarbeite_anfrage(input_pfad, ausgabe_ordner)
            erfolg = True
        except Exception as e:
            print(f"\n❌ Pipeline-Fehler: {e}")
            import traceback
            traceback.print_exc()
            erfolg = False

        dauer = time.time() - start
        print(f"\n⏱️  Gesamtdauer: {dauer:.2f}s")
