# ElringKlinger Quoting-Pipeline

End-to-End-Prototyp für AI-gestützte Angebots-Entwurfserstellung.

## Was die Pipeline tut

```
Mail/PDF/Excel  ─┐
                 ├─► Ingestion ─► Extraktion ─► Matching ─► Pricing ─► Draft-PDF
Stammdaten      ─┘       (LLM Vision)   (Rapidfuzz)   (SAP ZKALK mock)
```

1. **Ingestion** — Nimmt `.eml`, `.pdf`, `.xlsx` entgegen, trennt Mail-Body von Attachments
2. **Extraktion** — PDF-Seiten werden direkt als Bilder an GPT-5 (Vision) geschickt, keine OCR/Markdown-Zwischenstufe. Das ist der zentrale Design-Entscheid, weil klassische Markdown-Konverter bei mehrspaltigen Positionstabellen die Spaltenzuordnung verlieren.
3. **Matching** — Drei-Stufen-Matching der Artikelnummer gegen Stammdaten (exact → fuzzy → semantisch). Rein deterministisch, auditierbar.
4. **Pricing** — Deterministische Preisberechnung mit Mengenstaffel + SAP-ZKALK-Offset (Mock).
5. **Draft-PDF** — Angebots-Entwurf mit Positionstabelle, Warnhinweisen, Audit-Protokoll.

## Projektstruktur

```
quoting_pipeline/
├── src/
│   ├── pipeline.py       # CLI-Einstieg, orchestriert alle Schritte
│   ├── ingestion.py      # Mail-Parsing, Dateityp-Erkennung
│   ├── extractor.py      # Pydantic-Schema + LLM-Call (Vision)
│   ├── matching.py       # Fuzzy-Matching gegen Stammdaten
│   ├── pricing.py        # Preisberechnung
│   ├── output.py         # PDF-Generierung + JSON-Export
│   └── review_ui.py      # Streamlit Human-in-the-Loop UI
├── data/
│   ├── stammdaten.csv    # Artikel + Basispreise (Mock)
│   └── preise.csv        # Optional: separate Preistabelle
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt

# Azure OpenAI Key setzen (PowerShell)
$env:NEXUS_API_KEY="your_key_here"
```

## Nutzung

### CLI — Einzelne Anfrage verarbeiten

```bash
python -m src.pipeline Request_Preisanfrage_2026-50422.pdf
python -m src.pipeline eingang.eml --output C:\Angebote
```

### UI — Interaktive Review

```bash
streamlit run src/review_ui.py
```

Sales lädt die Anfrage hoch, prüft die extrahierten Felder (farblich nach Confidence), bestätigt/korrigiert, erstellt den Draft. Klassischer Human-in-the-Loop-Workflow.

## Warum keine OCR + Markdown-Pipeline?

Die erste Iteration nutzte MarkItDown für alle PDFs. Bei der Göhmann-Anfrage zeigte sich: Positionstabellen werden zeilenweise linearisiert, dabei geht die Spaltenzuordnung verloren — Artikelnummern, Mengen und Beschreibungen landen in getrennten Textblöcken, das LLM muss die Zuordnung raten.

Vision-basierte Extraktion löst das, weil das Modell das Layout visuell wahrnimmt. Kosten pro Anfrage sind etwas höher, aber die Extraktions-Qualität ist deutlich besser und das Debugging (via `source_quote` pro Feld) wird einfacher.

## Erweiterungspunkte

- **Echte SAP-Anbindung** — `pricing.py::lade_preise()` gegen SAP-API tauschen
- **Embeddings für Matching** — `matching.py` um `sentence-transformers` erweitern für semantische Artikel-Suche bei Freitext-Bezeichnungen
- **Batch-Verarbeitung** — IMAP-Poller um `verarbeite_anfrage()` herumbauen
- **Feedback-Loop** — Korrekturen der Sales-User zurück ins System loggen, für späteres Feintuning

## Lizenz-Status aller Dependencies

Alle verwendeten Bibliotheken permissive (MIT/Apache 2.0/BSD) — keine Copyleft-Probleme für kommerzielle Nutzung.
