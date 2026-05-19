"""Pipeline orchestrator.

Wires the four standard steps together for a full end-to-end run, but
also exposes each step individually so callers can re-run, replay, or
customise the flow:

    pipeline = QuotingPipeline()

    # End-to-end:
    result = pipeline.run(mail, output_dir=Path("out"), work_name="rfq42")

    # Or step-by-step (e.g. from the review UI):
    ctx = StepContext(work_dir=Path("out/rfq42"))
    anfrage   = pipeline.extract(mail, ctx)
    matches   = pipeline.match(anfrage, ctx)
    quotation = pipeline.price(anfrage, matches, ctx)
    pdf       = pipeline.render(anfrage, quotation, Path("out/rfq42/x.pdf"), ctx)

Each step is configured once at construction time. Pass custom step
instances to swap an implementation without touching the orchestrator —
this is the documented way to slot in a Rust matcher later.

Master data is reached through the
:class:`quoting.data.StammdatenRepository` boundary. The default is a
CSV-backed repository; injecting a SQL or SAP-backed one only requires
passing it to the constructor::

    pipeline = QuotingPipeline(stammdaten_repo=MySapRepo(...))
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core import Anfrage, Settings, add_file_handler, get_logger, load_settings
from ..data import StammdatenRepository, build_repository
from ..extraction.fast_path import FastPathExtractor
from ..extraction.own_party import load_own_party_context, sanitize_own_customer_fields
from ..ingestion import Mail
from ..matching import MatchResult
from ..pricing import Quotation
from .context import StepContext
from .progress import ProgressCallback, noop_progress
from .result import PipelineResult
from .steps import (
    ExtractionStep,
    MatchingStep,
    PricingStep,
    PythonMatcher,
    RenderStep,
)

log = get_logger()


class QuotingPipeline:
    """Reusable pipeline. Loads stammdaten once, configures steps once."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        stammdaten_repo: StammdatenRepository | None = None,
        extraction_step: ExtractionStep | None = None,
        matching_step: MatchingStep | None = None,
        pricing_step: PricingStep | None = None,
        render_step: RenderStep | None = None,
    ):
        self.settings = settings or load_settings()
        self._stammdaten_repo = stammdaten_repo
        self._extraction = extraction_step or ExtractionStep(self.settings)
        self._matching = matching_step
        self._pricing = pricing_step or PricingStep(self.settings.preise_path)
        self._render = render_step or RenderStep()
        self._fast_path: FastPathExtractor | None = None

    # ---------- shared resources ----------------------------------------

    @property
    def stammdaten_repo(self) -> StammdatenRepository:
        """The configured master-data repository (built lazily)."""
        if self._stammdaten_repo is None:
            self._stammdaten_repo = build_repository(self.settings.stammdaten_path)
        return self._stammdaten_repo

    @property
    def stammdaten(self) -> list[dict]:
        """Master data in the legacy ``list[dict]`` shape.

        Kept for back-compat with code that still expects rows. New
        callers should prefer :attr:`stammdaten_repo`.
        """
        return self.stammdaten_repo.as_rows()

    @property
    def fast_path(self) -> FastPathExtractor:
        """Deterministic Aho-Corasick extractor over the article-nr lexicon."""
        if self._fast_path is None:
            self._fast_path = FastPathExtractor(self.stammdaten_repo)
        return self._fast_path

    @property
    def matching(self) -> MatchingStep:
        if self._matching is None:
            self._matching = MatchingStep(
                matcher=PythonMatcher(
                    fuzzy_threshold=self.settings.fuzzy_threshold,
                    semantic_threshold=self.settings.semantic_threshold,
                ),
                stammdaten=self.stammdaten,
            )
        return self._matching

    # ---------- end-to-end ----------------------------------------------

    def run(
        self,
        mail: Mail,
        output_dir: Path | None = None,
        work_name: str | None = None,
        progress: ProgressCallback | None = None,
        *,
        is_final: bool = False,
        company_profile: Any | None = None,
        snapshot_sink: Callable[[str, Any], None] | None = None,
    ) -> PipelineResult:
        """Run all four steps in sequence."""
        if not mail.has_content:
            raise ValueError(
                "Mail has neither body nor attachments — nothing to extract."
            )
        output_dir = output_dir or self.settings.output_dir
        work_dir = output_dir / (work_name or _derive_work_name(mail))
        work_dir.mkdir(parents=True, exist_ok=True)
        add_file_handler(work_dir / "run.log")
        log.info("=" * 60)
        log.info("Subject     : %s", mail.subject or "(no subject)")
        log.info("From        : %s", mail.sender or "(unknown)")
        log.info("Body length : %d chars", len(mail.body))
        log.info("Attachments : %d", len(mail.attachments))
        log.info("Work dir    : %s", work_dir)
        ctx = StepContext(
            work_dir=work_dir,
            progress=progress or noop_progress,
            snapshot_sink=snapshot_sink,
        )
        start = time.time()
        anfrage = self.extract(mail, ctx)
        matches = self.match(anfrage, ctx)
        quotation = self.price(anfrage, matches, ctx)
        pdf_path = self.render(
            anfrage,
            quotation,
            work_dir / f"{work_dir.name}_ANGEBOT_DRAFT.pdf",
            ctx,
            is_final=is_final,
            company_profile=company_profile,
        )
        duration = time.time() - start
        log.info("Done in %.2fs - total %.2f EUR",
                 duration, quotation.gesamtsumme)
        return PipelineResult(
            mail=mail,
            work_dir=work_dir,
            anfrage=anfrage,
            matches=matches,
            quotation=quotation,
            pdf_path=pdf_path,
            duration_s=duration,
            token_usage=ctx.extra.get("token_usage"),
            extraction_path=ctx.extra.get("extraction_path"),
        )

    # ---------- individual steps ----------------------------------------

    def extract(self, mail: Mail, ctx: StepContext) -> Anfrage:
        # Try the deterministic fast-path first. It returns None whenever
        # the input isn't unambiguously trivial (no article-nr hit, no
        # quantity in window, multi-article without per-article quantity)
        # so the LLM fallback handles the messy cases.
        anfrage = self.fast_path.try_extract(mail)
        if anfrage is not None:
            cleared = sanitize_own_customer_fields(anfrage, load_own_party_context())
            if cleared:
                log.info("Fast-path cleared own customer field(s): %s", ", ".join(cleared))
            ctx.report(
                self._extraction.name,
                "completed",
                f"{len(anfrage.positionen)} Positionen (Fast-Path)",
            )
            ctx.extra["extraction_path"] = "fast_path"
            ctx.persist("extracted", anfrage.model_dump(mode="json"))
            for pos in anfrage.positionen:
                log.info(
                    "  Pos %d [%s]: %s x%s - %s",
                    pos.pos_nr, pos.confidence, pos.artikelnummer,
                    pos.menge, pos.bezeichnung[:50],
                )
            return anfrage
        ctx.extra["extraction_path"] = "llm"
        anfrage = self._extraction.run(mail, ctx)
        cleared = sanitize_own_customer_fields(anfrage, load_own_party_context())
        if cleared:
            log.info("Extraction cleared own customer field(s): %s", ", ".join(cleared))
            ctx.persist("extracted", anfrage.model_dump(mode="json"))
        return anfrage

    def match(self, anfrage: Anfrage, ctx: StepContext) -> list[MatchResult]:
        return self.matching.run(anfrage, ctx)

    def price(
        self,
        anfrage: Anfrage,
        matches: list[MatchResult],
        ctx: StepContext,
    ) -> Quotation:
        return self._pricing.run(anfrage, matches, ctx)

    def render(
        self,
        anfrage: Anfrage,
        quotation: Quotation,
        output_path: Path,
        ctx: StepContext,
        *,
        is_final: bool = False,
        company_profile: Any | None = None,
    ) -> Path:
        # If caller didn't override the step, use a one-off render step
        # that knows about approval state and company profile. Otherwise
        # respect the injected step.
        if isinstance(self._render, RenderStep) and (is_final or company_profile is not None):
            step = RenderStep(is_final=is_final, company_profile=company_profile)
        else:
            step = self._render
        return step.run(anfrage, quotation, output_path, ctx)


def _derive_work_name(mail: Mail) -> str:
    """Pick a reasonable folder name for this run."""
    if mail.attachments:
        return mail.attachments[0].stem
    if mail.subject:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in mail.subject)
        return safe[:80] or "run"
    return "run"
