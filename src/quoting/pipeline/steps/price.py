"""Pricing step — Anfrage + matches → Quotation.

Pure deterministic calculation. No LLM, no I/O beyond reading the price
override CSV.
"""
from __future__ import annotations

from pathlib import Path

from ...core import Anfrage, get_logger
from ...matching import MatchResult
from ...pricing import Quotation, build_quotation
from ..context import StepContext

log = get_logger()


class PricingStep:
    name = "Preisberechnung"

    def __init__(self, prices_path: Path):
        self.prices_path = prices_path

    def run(
        self,
        anfrage: Anfrage,
        matches: list[MatchResult],
        ctx: StepContext,
    ) -> Quotation:
        ctx.report(self.name, "started")
        log.info("Price: calculating...")

        try:
            quotation = build_quotation(anfrage, matches, self.prices_path)
        except Exception as exc:
            ctx.report(self.name, "failed", str(exc))
            raise

        ctx.persist("quotation", quotation.to_dict())
        ctx.report(
            self.name,
            "completed",
            f"Gesamt: {quotation.gesamtsumme:.2f} {quotation.waehrung}",
        )
        return quotation
