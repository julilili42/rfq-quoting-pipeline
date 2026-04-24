# Architecture

## Data flow

```
┌───────────┐    ┌────────────┐    ┌───────────┐    ┌──────────┐    ┌────────┐
│ Ingestion │───>│ Extraction │───>│ Matching  │───>│ Pricing  │───>│ Output │
│           │    │   (LLM)    │    │(Stammdtn) │    │ (Rules)  │    │  PDF   │
└───────────┘    └────────────┘    └───────────┘    └──────────┘    └────────┘
  eml/pdf/xlsx    Anfrage +         MatchResult[]    Quotation       PDF+JSON
                  Position[]
```

## Module dependencies

- `core/` depends on nothing.
- Every stage depends on `core/` only.
- `pipeline.py` depends on every stage.
- Stages do **not** depend on each other. Data flows through them via
  `pipeline.py`; they do not import from sibling stages.

This is enforced by the directory structure: if you catch yourself writing
`from quoting.matching import X` inside `quoting/pricing/…`, stop and route
the call through `pipeline.py` or lift the shared type into `core/`.

## What lives where

| Concern | Location | Rationale |
|---------|----------|-----------|
| LLM prompt | `extraction/prompts.py` | prompt engineering is isolated from wiring |
| Retry logic | `extraction/llm/base.py` | only LLM calls are flaky |
| Discount tiers | `pricing/discounts.py` | business rule, likely to change |
| PDF layout | `output/pdf_builder.py` | swap reportlab → weasyprint later w/o touching pipeline |

## What pipeline.py writes to disk

Per RFQ, under `<output_dir>/<input-stem>/`:
- `01_extracted.json` — raw extraction, for audit
- `02_matches.json` — matching results with scores
- `03_quotation.json` — final priced quotation (source of truth)
- `<name>_ANGEBOT_DRAFT.pdf` — the deliverable
- `run.log` — per-run log (structured)
