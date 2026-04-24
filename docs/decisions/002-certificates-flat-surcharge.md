# ADR 002: Certificates are flat surcharges

## Status
Accepted

## Context
RFQs often include items like `Abnahmeprüfzeugnis 3.1` or `EN 10204 Werks-
zeugnis`. These are documents, not physical parts. The customer usually
writes them on a dedicated line with `Menge = 1`, but some write
`Menge = <anzahl der Teile>` so the certificate quantity matches the part
count.

If treated as a normal line item, a certificate at quantity 1000 would:
1. Trigger the 15% volume discount.
2. Get multiplied by 1000.
Result: a €45 surcharge becomes €38,250 on the draft quotation.

## Decision
- The LLM flags certificate lines via `Position.ist_zertifikat = true`.
- Pricing treats certificates specially:
  - No volume discount (rabatt = 0).
  - `gesamtpreis = einzelpreis` regardless of `menge`.
- The draft PDF shows `Certificate - flat surcharge` in the Hinweis column.

## Consequences
- The prompt must list certificate keywords explicitly
  (`Abnahmeprüfzeugnis`, `EN 10204`, `Werkszeugnis`). If Sales encounters a
  new phrasing, add it to `prompts.py` and a test case.
- If a certificate actually should be per-piece (unusual), Sales can override
  the flag in the review UI before finalizing.
- Covered by `tests/unit/test_pricing.py::test_certificate_is_flat_surcharge_no_discount`.
