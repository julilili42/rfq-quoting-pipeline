"""Rendering step — Quotation → PDF (or JSON fallback)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core import Anfrage, get_logger
from ...output import build_draft_pdf
from ...pricing import Quotation
from ..context import StepContext

log = get_logger()


class RenderStep:
    name = "PDF-Rendering"

    def __init__(
        self,
        *,
        is_final: bool = False,
        company_profile: Any | None = None,
    ):
        self.is_final = is_final
        self.company_profile = company_profile

    def run(
        self,
        anfrage: Anfrage,
        quotation: Quotation,
        output_path: Path,
        ctx: StepContext,
    ) -> Path:
        ctx.report(self.name, "started", output_path.name)
        log.info("Render: PDF -> %s (final=%s)", output_path, self.is_final)

        try:
            build_draft_pdf(
                anfrage,
                quotation,
                output_path,
                is_final=self.is_final,
                company_profile=self.company_profile,
            )
        except Exception as exc:
            ctx.report(self.name, "failed", str(exc))
            raise

        ctx.report(self.name, "completed", str(output_path))
        return output_path
