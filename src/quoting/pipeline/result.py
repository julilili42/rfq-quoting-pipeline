"""Result of a full end-to-end pipeline run."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core import Anfrage
from ..ingestion import Mail
from ..matching import MatchResult
from ..pricing import Quotation


@dataclass
class PipelineResult:
    mail: Mail
    work_dir: Path
    anfrage: Anfrage
    matches: list[MatchResult]
    quotation: Quotation
    pdf_path: Path
    duration_s: float

    def summary(self) -> dict:
        return {
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
