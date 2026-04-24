# ElringKlinger Quoting Pipeline

AI-assisted draft quotation generator: RFQ (PDF / Mail / Excel) → structured extraction → master-data matching → draft PDF quotation.

## Pipeline flow

```
  ingestion ──► extraction ──► matching ──► pricing ──► output
  (eml/pdf)    (LLM)          (fuzzy)      (rules)    (PDF+JSON)
```

Each stage lives in its own sub-package under `src/quoting/`. The only place stage order is encoded is `pipeline.py`, which reads like a table of contents.

## Layout

```
quoting-pipeline/
├── README.md
├── pyproject.toml
├── .env.example
├── run_ui.py                  # Streamlit launcher
│
├── data/                      # master data, price tables
├── samples/                   # example RFQs for manual testing
├── docs/                      # architecture notes, ADRs
│   └── decisions/
│
├── src/quoting/
│   ├── cli.py                 # run / batch entry point
│   ├── pipeline.py            # orchestrator — reads top-to-bottom
│   │
│   ├── core/                  # cross-stage basics
│   │   ├── config.py          # Settings (frozen dataclass)
│   │   ├── logging_setup.py
│   │   └── schema.py          # Anfrage, Position (Pydantic)
│   │
│   ├── ingestion/             # input → body + attachments
│   │   ├── file_types.py
│   │   └── mail.py
│   │
│   ├── extraction/            # attachments → Anfrage (LLM-powered)
│   │   ├── extractor.py
│   │   ├── document_loader.py
│   │   ├── prompts.py
│   │   ├── json_utils.py
│   │   └── llm/               # provider abstraction (internal)
│   │       ├── base.py
│   │       ├── factory.py
│   │       ├── gemini.py
│   │       └── azure.py
│   │
│   ├── matching/              # Anfrage → MatchResults (deterministic)
│   │   ├── matcher.py
│   │   └── stammdaten.py
│   │
│   ├── pricing/               # Anfrage + matches → Quotation
│   │   ├── quotation.py
│   │   ├── discounts.py
│   │   └── prices.py
│   │
│   ├── output/                # Quotation → PDF + JSON
│   │   ├── pdf_builder.py
│   │   └── json_writer.py
│   │
│   └── ui/                    # Streamlit review
│       └── review_app.py
│
├── tests/
│   ├── unit/                  # fast, no I/O
│   ├── integration/           # filesystem + mocks, no real LLM
│   └── fixtures/
│
└── scripts/                   # ad-hoc tools, not part of the pipeline
```

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
# fill in GOOGLE_API_KEY or NEXUS_API_KEY
```

## Usage

```bash
# Single file
python -m quoting.cli run path/to/rfq.pdf

# Batch a folder
python -m quoting.cli batch ./inbox --output ./results

# Review UI
streamlit run run_ui.py
```

## Tests

```bash
pytest                      # all
pytest tests/unit           # fast core only
```

## Design decisions

Details in `docs/decisions/`. Key ones:

- **No LLM in matching or pricing.** Only extraction is non-deterministic; everything downstream is reproducible and auditable.
- **LLM clients are hidden inside `extraction/llm/`.** No other module is allowed to call them. Enforced by package structure.
- **Certificates are flat surcharges.** `ist_zertifikat=True` → no volume discount, no qty multiplication.

## What changed vs v0.2

- Renamed package `src` → `src/quoting` (proper src-layout).
- Flat stage folders: `ingestion/`, `extraction/`, `matching/`, `pricing/`, `output/`, `ui/` — each with an `__init__.py` that defines the public API.
- LLM clients moved to `extraction/llm/` (they're an implementation detail of that stage, not a cross-cutting concern).
- `pricing` split into `discounts.py` + `prices.py` + `quotation.py`.
- `matching` split into `matcher.py` + `stammdaten.py`.
- `output` split into `pdf_builder.py` + `json_writer.py`.
- Imports now use absolute paths (`from quoting.core import ...`) which work with both `python -m quoting.cli` and `streamlit run run_ui.py`.
