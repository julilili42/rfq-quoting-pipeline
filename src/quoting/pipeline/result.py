"""Result of a full end-to-end pipeline run."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..core import Anfrage
from ..ingestion import Mail
from ..matching import MatchResult
from ..pricing import Quotation

if TYPE_CHECKING:
    from ..extraction.llm.base import TokenUsage


@dataclass
class PipelineResult:
    mail: Mail
    work_dir: Path
    anfrage: Anfrage
    matches: list[MatchResult]
    quotation: Quotation
    pdf_path: Path
    duration_s: float
    token_usage: TokenUsage | None = field(default=None)
    # "fast_path" = deterministic AC + quantity match, no LLM call.
    # "llm"       = Gemini/Azure extraction.
    # None        = unknown (older runs / non-standard pipelines).
    extraction_path: str | None = field(default=None)

    def summary(self) -> dict:
        result: dict = {
            "subject": self.mail.subject,
            "sender": self.mail.sender,
            "attachments": [a.name for a in self.mail.attachments],
            "positions": len(self.anfrage.positionen),
            "exact": sum(1 for m in self.matches if m.status == "exact"),
            "fuzzy": sum(1 for m in self.matches if m.status == "fuzzy"),
            "semantic": sum(1 for m in self.matches if m.status == "semantic"),
            "no_match": sum(1 for m in self.matches if m.status == "no_match"),
            "total_eur": self.quotation.gesamtsumme,
            "duration_s": round(self.duration_s, 2),
            "pdf": str(self.pdf_path),
        }
        if self.token_usage is not None:
            result["token_usage"] = {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "total_tokens": self.token_usage.total_tokens,
            }
        if self.extraction_path is not None:
            result["extraction_path"] = self.extraction_path
        return result
