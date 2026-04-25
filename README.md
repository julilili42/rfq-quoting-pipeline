# ElringKlinger Quoting Pipeline

AI-assisted draft quotation generator: RFQ (PDF / Mail / Excel) → structured extraction → master-data matching → draft PDF quotation.

## Pipeline flow

```text
ingestion ──► extraction ──► matching ──► pricing ──► output
(eml/pdf/xlsx) (LLM)        (fuzzy)      (rules)    (PDF+JSON)
```

Each stage lives in its own sub-package under `src/quoting/`. The only place where the stage order is encoded is `pipeline.py`.

## Environment configuration

The project uses `python-dotenv` and loads local environment variables from a `.env` file.

A template is provided in `.env.example`. Copy it once and fill in the required values locally:

```bash
cp .env.example .env
```

The `.env` file must not be committed because it can contain API keys and secrets.

Minimum configuration for local extraction:

```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-google-api-key
```

For Azure OpenAI / Nexus:

```bash
LLM_PROVIDER=azure
NEXUS_API_KEY=your-nexus-api-key
AZURE_OPENAI_ENDPOINT=https://genai-nexus.api.corpinter.net/
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_MODEL=gpt-5-mini
```

Optional runtime paths:

```bash
OUTPUT_DIR=./output
DATA_DIR=./data
```

## Layout

```text
quoting-pipeline/
├── README.md
├── pyproject.toml
├── .env.example              # environment variable template
├── .env                      # local secrets, ignored by git
├── run_ui.py                 # manual upload / review UI launcher
├── run_app.py                # combined launcher for UI + optional Outlook sync
├── run_inbox.py              # inbox dashboard launcher, requires inbox_app.py
│
├── data/
│   └── stammdaten_test.csv
│
├── docs/
│   ├── architecture.md
│   └── decisions/
│
├── samples/
│   └── README.md
│
├── scripts/
│   ├── smoke_test.py
│   └── sync_outlook.py
│
├── src/quoting/
│   ├── cli.py                # run / batch entry point
│   ├── pipeline.py           # orchestrator
│   │
│   ├── core/                 # config, logging, schema
│   ├── ingestion/            # file / mail parsing
│   ├── extraction/           # LLM extraction
│   ├── matching/             # deterministic master-data matching
│   ├── pricing/              # deterministic pricing
│   ├── output/               # PDF + JSON output
│   ├── outlook/              # Microsoft Graph / Outlook integration
│   └── ui/                   # Streamlit apps
│       └── review_app.py
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

## Setup

Install the project in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

Create the local environment file:

```bash
cp .env.example .env
```

Then edit `.env` and add the required API keys.

## How to start the app

### Manual upload / review UI

Use this for local testing with PDF, EML, XLSX or CSV files:

```bash
streamlit run run_ui.py
```

Alternative:

```bash
python run_app.py --app review --no-sync
```

### Combined launcher with Outlook sync

Only use this if the Outlook integration is configured and the inbox UI exists:

```bash
python run_app.py
```

Required Outlook environment variables:

```bash
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
OUTLOOK_MAILBOX=
```

Optional Outlook variables:

```bash
OUTLOOK_FOLDER=Inbox
OUTLOOK_PROCESSED_FOLDER=AI-Processed
OUTLOOK_POLL_SECONDS=60
OUTLOOK_MAX_FETCH=25
OUTLOOK_STORE_DIR=./data/outlook_cache
```

Note: `run_app.py` defaults to the inbox dashboard. This requires:

```text
src/quoting/ui/inbox_app.py
```

If that file is not present, start the review UI instead:

```bash
python run_app.py --app review --no-sync
```

## CLI usage

Process one file:

```bash
python -m quoting.cli run path/to/rfq.pdf
```

Process a folder:

```bash
python -m quoting.cli batch ./inbox --output ./results
```

Supported input files:

```text
.pdf
.eml
.xlsx
.xls
.csv
```

## Tests

Run all tests:

```bash
pytest
```

Run only unit tests:

```bash
pytest tests/unit
```

## Notes

- Extraction uses an LLM provider configured via `.env`.
- Matching and pricing are deterministic and do not use an LLM.
- Generated outputs are written to `OUTPUT_DIR`.
- Local secrets belong in `.env`, not in version control.