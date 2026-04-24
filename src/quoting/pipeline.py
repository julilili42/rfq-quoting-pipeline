"""End-to-end pipeline orchestrator.

Stages in order:
  1. ingest    - file -> body + attachments
  2. extract   - attachments -> Anfrage (LLM)
  3. match     - positions -> MatchResults (deterministic)
  4. price     - Anfrage + matches -> Quotation
  5. render    - Quotation -> draft PDF + JSON

Each stage lives in its own sub-package. This file is the only place where
their order is encoded.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .core import Anfrage, Settings, add_file_handler, get_logger, load_settings
from .extraction import extract_anfrage
from .ingestion import detect_file_type, parse_mail
from .matching import MatchResult, load_stammdaten, match_positions
from .output import build_draft_pdf, save_json
from .pricing import Quotation, build_quotation

log = get_logger()


@dataclass
class PipelineResult:
    input_path: Path
    work_dir: Path
    anfrage: Anfrage
    matches: list[MatchResult]
    quotation: Quotation
    pdf_path: Path
    duration_s: float

    def summary(self) -> dict:
        return {
            "input": str(self.input_path),
            "positions": len(self.anfrage.positionen),
            "exact": sum(1 for m in self.matches if m.status == "exact"),
            "fuzzy": sum(1 for m in self.matches if m.status == "fuzzy"),
            "semantic": sum(1 for m in self.matches if m.status == "semantic"),
            "no_match": sum(1 for m in self.matches if m.status == "no_match"),
            "total_eur": self.quotation.gesamtsumme,
            "duration_s": round(self.duration_s, 2),
            "pdf": str(self.pdf_path),
        }


class QuotingPipeline:
    """Reusable pipeline instance. Cache-friendly: stammdaten loaded once."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._stammdaten: list[dict] | None = None

    @property
    def stammdaten(self) -> list[dict]:
        if self._stammdaten is None:
            self._stammdaten = load_stammdaten(self.settings.stammdaten_path)
        return self._stammdaten

    def run(
        self,
        input_path: Path,
        output_dir: Path | None = None,
        mail_body: str = "",
    ) -> PipelineResult:
        start = time.time()
        output_dir = output_dir or self.settings.output_dir
        work_dir = output_dir / input_path.stem
        work_dir.mkdir(parents=True, exist_ok=True)
        add_file_handler(work_dir / "run.log")

        log.info("=" * 60)
        log.info("Processing: %s", input_path.name)
        log.info("Work dir  : %s", work_dir)

        attachments, body = self._ingest(input_path, mail_body)
        anfrage = self._extract(attachments, body, work_dir)
        matches = self._match(anfrage, work_dir)
        quotation = self._price(anfrage, matches, work_dir)
        pdf_path = self._render(anfrage, quotation, input_path.stem, work_dir)

        duration = time.time() - start
        log.info("Done in %.2fs - total %.2f EUR", duration, quotation.gesamtsumme)
        return PipelineResult(
            input_path=input_path,
            work_dir=work_dir,
            anfrage=anfrage,
            matches=matches,
            quotation=quotation,
            pdf_path=pdf_path,
            duration_s=duration,
        )

    # ---------- individual stages ----------

    def _ingest(self, input_path: Path, mail_body: str) -> tuple[list[Path], str]:
        file_type = detect_file_type(input_path)
        log.info("Detected type: %s", file_type)

        if file_type == "eml":
            mail = parse_mail(input_path)
            log.info("Mail body: %d chars, %d attachment(s)",
                     len(mail.body), len(mail.attachments))
            return mail.attachments, mail.body
        if file_type in ("pdf", "xlsx", "csv"):
            return [input_path], mail_body
        raise ValueError(f"Unsupported input type: {file_type}")

    def _extract(
        self, attachments: list[Path], mail_body: str, work_dir: Path,
    ) -> Anfrage:
        log.info("Extract: LLM...")
        anfrage = extract_anfrage(attachments, mail_body, self.settings)
        save_json(anfrage.model_dump(mode="json"), work_dir / "01_extracted.json")
        for pos in anfrage.positionen:
            log.info("  Pos %d [%s]: %s x%s - %s",
                     pos.pos_nr, pos.confidence, pos.artikelnummer,
                     pos.menge, pos.bezeichnung[:50])
        return anfrage

    def _match(self, anfrage: Anfrage, work_dir: Path) -> list[MatchResult]:
        log.info("Match: against %d master-data rows...", len(self.stammdaten))
        matches = match_positions(
            anfrage.positionen,
            self.stammdaten,
            fuzzy_threshold=self.settings.fuzzy_threshold,
            semantic_threshold=self.settings.semantic_threshold,
        )
        for pos, m in zip(anfrage.positionen, matches):
            log.info("  Pos %d: %s (score %.2f)", pos.pos_nr, m.status, m.score)
        save_json([m.to_dict() for m in matches], work_dir / "02_matches.json")
        return matches

    def _price(
        self, anfrage: Anfrage, matches: list[MatchResult], work_dir: Path,
    ) -> Quotation:
        log.info("Price: calculating...")
        quotation = build_quotation(anfrage, matches, self.settings.preise_path)
        save_json(quotation.to_dict(), work_dir / "03_quotation.json")
        return quotation

    def _render(
        self, anfrage: Anfrage, quotation: Quotation,
        name: str, work_dir: Path,
    ) -> Path:
        log.info("Render: PDF...")
        pdf_path = work_dir / f"{name}_ANGEBOT_DRAFT.pdf"
        build_draft_pdf(anfrage, quotation, pdf_path)
        return pdf_path
