"""Rendering step — Quotation → PDF (or JSON fallback)."""
from __future__ import annotations

from pathlib import Path

from ...core import Anfrage, get_logger
from ...output import build_draft_pdf
from ...pricing import Quotation
from ..context import StepContext

log = get_logger()


class RenderStep:
    name = "PDF-Rendering"

    def run(
        self,
        anfrage: Anfrage,
        quotation: Quotation,
        output_path: Path,
        ctx: StepContext,
    ) -> Path:
        ctx.report(self.name, "started", output_path.name)
        log.info("Render: PDF -> %s", output_path)

        try:
            build_draft_pdf(anfrage, quotation, output_path)
        except Exception as exc:
            ctx.report(self.name, "failed", str(exc))
            raise

        ctx.report(self.name, "completed", str(output_path))
        return output_path
