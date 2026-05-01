# ElringKlinger Quoting Pipeline

KI-gestützter Generator für Angebotsentwürfe.
RFQ rein (PDF, Mail, Excel) → Angebotsentwurf raus (PDF + JSON).

```
ingestion → extraction → matching → pricing → output
            (LLM)        (fuzzy)    (rules)
```

Nur die Extraktion nutzt ein LLM. Matching und Pricing sind deterministisch
und voll auditierbar.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # API-Key eintragen (Gemini oder Azure)
```

Für das Outlook Add-in zusätzlich Node.js ≥ 20 und
[`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).

## Drei Wege zu starten

**CLI** — schnellster Sanity-Check.
```bash
python -m quoting.cli run path/to/rfq.pdf
python -m quoting.cli batch ./inbox --output ./results
```

**Streamlit Review-UI** — Datei hochladen, prüfen, freigeben.
```bash
python run_ui.py
```
Öffnet auf `http://localhost:8501`. In Schritt 3 gibt es einen
`⛶ Vollbild`-Button für den fokussierten Vergleich Original ↔ Entwurf.

**Outlook Add-in** — End-to-End aus dem Postfach. Drei Terminals:
```bash
python run_review_api.py            # FastAPI + cloudflared-Tunnel
python run_ui.py                    # Streamlit UI
cd outlook-test-addin && npm run dev # Vite Dev Server (HTTPS:5173)
```
Add-in einmalig in Outlook laden via `outlook-test-addin/manifest.xml`.
Mail öffnen → Ribbon-Button **TEST** → "Draft Quotation erstellen".

`run_review_api.py` schreibt die aktive Tunnel-URL nach `.tunnel_url`,
die FastAPI liest sie pro Request — kein manuelles Editieren nötig.

## Layout

```
src/quoting/
├── cli.py                # CLI entry point
├── api/                  # FastAPI für Outlook Add-in
├── core/                 # config, logging, schema
├── ingestion/            # .eml / .msg / loose file parsing
├── extraction/           # LLM extraction (Gemini / Azure)
├── matching/             # deterministisches Matching
├── pricing/              # deterministisches Pricing
├── output/               # PDF + JSON writer
├── pipeline/             # Orchestrator + Steps
└── ui/                   # Streamlit Review-App

data/
├── stammdaten_test.csv   # Beispiel-Stammdaten
└── reviews/              # Pro-Review-Artefakte
```

ADRs in `docs/decisions/`. Architektur-Notizen in `docs/architecture.md`.

## Tests

```bash
pytest                  # alle
pytest tests/unit       # nur Unit
```
