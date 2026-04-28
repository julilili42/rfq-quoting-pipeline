"""Pipeline package: ingest a Mail, produce a draft quotation PDF.

The pipeline is split into self-contained steps (see ``steps/``). Each step
is a class with a tight ``run()`` signature, owns its own logging, and
persists its output as a numbered JSON snapshot in the work dir.

Two ways to use the package:

1. **End-to-end** — the common path. Construct a ``QuotingPipeline``,
   call ``run(mail, output_dir, work_name)``. Stammdaten and the LLM
   client are loaded once and reused.

2. **Per-step** — for the review UI, retries, or debugging. Call
   ``pipeline.extract(mail, ctx)``, ``pipeline.match(anfrage, ctx)``
   etc. directly. Each step's input is the previous step's output, so
   you can re-run any subset.

Swapping a step (e.g. a Rust matcher) is done at construction time:

    pipeline = QuotingPipeline(
        matching_step=MatchingStep(matcher=MyRustMatcher(), stammdaten=...)
    )
"""
from .context import StepContext
from .orchestrator import QuotingPipeline
from .progress import ProgressCallback, StepProgress, StepStatus, noop_progress
from .result import PipelineResult
from .steps import (
    ExtractionStep,
    Matcher,
    MatchingStep,
    PricingStep,
    PythonMatcher,
    RenderStep,
)

__all__ = [
    "QuotingPipeline",
    "PipelineResult",
    "StepContext",
    "StepProgress",
    "StepStatus",
    "ProgressCallback",
    "noop_progress",
    "ExtractionStep",
    "MatchingStep",
    "Matcher",
    "PythonMatcher",
    "PricingStep",
    "RenderStep",
]
