# 003 · Stammdaten access via repository abstraction

**Status:** accepted
**Date:** 2026-04
**Context:** prototype is moving from a hand-crafted toy CSV to historical
SAP offer data. Production will eventually read from SAP / a SQL view.

## Decision

All master-data reads go through a `StammdatenRepository` Protocol
defined in `quoting.data.repository`. The default implementation
(`CsvStammdatenRepository`) reads `data/stammdaten.csv`, which is
generated offline from the raw `Overview_Offers.xlsx` export by
`python -m quoting.data.prep.build_stammdaten`.

```text
Overview_Offers.xlsx  ──[ build_stammdaten ]──►  data/stammdaten.csv
                                                         │
                                                         ▼
                                          CsvStammdatenRepository
                                                         │
                                                         │  StammdatenRepository
                                                         ▼
                                            QuotingPipeline · MatchingStep
```

The matcher and pricing modules continue to consume `list[dict]` (via
`StammdatenRepository.as_rows()`) so this change introduces *zero*
behavioural risk to the matching tier. New code should depend on
`StammdatenRecord` and `StammdatenRepository` directly.

## Why a repository, not direct file access

* **Replaceability.** Swapping the CSV for SQL / SAP / an HTTP service
  is a constructor argument away — no caller changes.
* **Testability.** `InMemoryStammdatenRepository` lets unit tests build
  fixtures inline without temp files.
* **Caching boundary.** The repo is the obvious place to cache results
  and (later) invalidate when the source changes.

## Why keep the `list[dict]` shape on the consumer boundary

Refactoring the matcher to consume `StammdatenRecord` would touch
hot, well-tested code for no behavioural gain. The `to_row()` /
`as_rows()` adaptor is cheap and keeps the diff small. We can migrate
the matcher later if a typed access pattern proves valuable.

## Consequences

* `data/stammdaten_test.csv` (the hand-crafted file) is no longer the
  canonical input — but `Settings.stammdaten_path` falls back to it so
  legacy workspaces still work.
* The data-prep script needs `pandas` + `openpyxl`. Both are dev-only
  dependencies; the runtime path uses only stdlib `csv`.
* Future SQL/SAP adapters live next to `CsvStammdatenRepository` in
  `quoting/data/repository.py` (or split out once a second adapter
  lands).
