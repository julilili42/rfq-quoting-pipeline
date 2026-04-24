# ADR 001: No LLM in matching or pricing

## Status
Accepted

## Context
An RFQ pipeline is tempting to "LLM-ify" end-to-end: let the model not only
read the PDF but also pick the matching article, compute the price, and write
the quotation. This is cheap to build but creates two problems:

1. **Non-reproducibility.** The same input may yield different prices on
   different runs. Sales cannot audit why.
2. **No ground truth for regression.** If a customer disputes a price,
   "the LLM said so" is not a defensible answer.

## Decision
- The LLM is used **only** in the extraction stage (`src/quoting/extraction/`).
- Matching is deterministic: exact normalization, fuzzy string distance, or
  weighted description/material score. Inputs and thresholds are version-
  controlled, outputs are reproducible bit-for-bit given the same stammdaten.
- Pricing is rule-based: discount tiers, ZKALK offset, certificate-flat rule.

## Consequences
- Adding a new matching signal (e.g. dimensions) means writing deterministic
  code, not tweaking a prompt.
- All pricing disputes can be traced to specific rule + input data.
- The LLM's surface is small enough to test (does it extract the right
  positions from fixture PDFs?).
- If matching accuracy plateaus, we can add a *ranked* LLM suggestion on
  top — but the first-cut match will always be deterministic.
