"""Matching step — positions → master-data hits.

The actual matching algorithm lives behind a ``Matcher`` Protocol, so
the step itself is a thin wrapper. The default ``PythonMatcher`` uses
the deterministic three-tier rapidfuzz matcher from ``quoting.matching``.

Swapping for a Rust implementation later
----------------------------------------
Build a class that implements ``Matcher`` (e.g. via PyO3) and pass it
to the step::

    rust_matcher = MyRustMatcher(...)
    step = MatchingStep(matcher=rust_matcher, stammdaten=stammdaten)
    pipeline = QuotingPipeline(matching_step=step)

Nothing else in the pipeline needs to change — the orchestrator only
ever sees the ``MatchingStep`` interface.
"""
from __future__ import annotations

from typing import Protocol

from ...core import Anfrage, Position, get_logger
from ...matching import MatchResult, match_positions
from ..context import StepContext

log = get_logger()


class Matcher(Protocol):
    """Maps a list of positions to match results.

    The interface is intentionally tiny: take positions + stammdaten,
    return one result per position. Thresholds, scoring, and any other
    config are implementation details of the matcher.
    """

    def match(
        self,
        positions: list[Position],
        stammdaten: list[dict],
    ) -> list[MatchResult]: ...


class PythonMatcher:
    """Default matcher: rapidfuzz-based three-tier matching."""

    def __init__(self, fuzzy_threshold: int = 85, semantic_threshold: int = 70):
        self.fuzzy_threshold = fuzzy_threshold
        self.semantic_threshold = semantic_threshold

    def match(
        self,
        positions: list[Position],
        stammdaten: list[dict],
    ) -> list[MatchResult]:
        return match_positions(
            positions,
            stammdaten,
            fuzzy_threshold=self.fuzzy_threshold,
            semantic_threshold=self.semantic_threshold,
        )


class MatchingStep:
    """Run any ``Matcher`` against the loaded master data."""

    name = "Matching"

    def __init__(self, matcher: Matcher, stammdaten: list[dict]):
        self.matcher = matcher
        self.stammdaten = stammdaten

    def run(self, anfrage: Anfrage, ctx: StepContext) -> list[MatchResult]:
        ctx.report(
            self.name,
            "started",
            f"{len(anfrage.positionen)} Positionen vs. {len(self.stammdaten)} Stammdaten",
        )
        log.info("Match: %d position(s) against %d row(s)",
                 len(anfrage.positionen), len(self.stammdaten))

        try:
            matches = self.matcher.match(anfrage.positionen, self.stammdaten)
        except Exception as exc:
            ctx.report(self.name, "failed", str(exc))
            raise

        for pos, m in zip(anfrage.positionen, matches):
            log.info("  Pos %d: %s (score %.2f)", pos.pos_nr, m.status, m.score)

        ctx.persist("02_matches.json", [m.to_dict() for m in matches])

        exact = sum(1 for m in matches if m.status == "exact")
        no_match = sum(1 for m in matches if m.status == "no_match")
        ctx.report(
            self.name,
            "completed",
            f"{exact} exakt, {no_match} kein Treffer",
        )
        return matches
