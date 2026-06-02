"""Extraction step — Mail → Anfrage via LLM.

This is the only LLM-dependent step. To swap it (e.g. with a different
model, a deterministic parser for known templates, or a hybrid), pass a
custom ``ExtractionStep``-shaped object to ``QuotingPipeline``.
"""
from __future__ import annotations

from ...core import Anfrage, Settings, get_logger
from ...extraction import extract_anfrage
from ...ingestion import Mail
from ..context import StepContext

log = get_logger()


class ExtractionStep:
    name = "Extraktion"

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, mail: Mail, ctx: StepContext) -> Anfrage:
        ctx.report(
            self.name,
            "started",
            f"{len(mail.attachments)} Anhang/Anhänge"
            if mail.attachments
            else "nur Mail-Body",
        )
        log.info(
            "Extract: LLM with %d attachment(s)%s",
            len(mail.attachments),
            "" if mail.attachments else " (body only)",
        )

        try:
            anfrage, token_usage = extract_anfrage(
                attachments=mail.attachments,
                mail_body=mail.body,
                settings=self.settings,
                on_llm_retry=lambda event: ctx.report(
                    self.name,
                    "started",
                    (
                        f"{event['provider']}: Versuch "
                        f"{event['next_attempt']}/{event['max_attempts']}"
                    ),
                    metadata={"llm_retry": event},
                ),
            )
            if token_usage is not None:
                ctx.extra["token_usage"] = token_usage
        except Exception as exc:
            ctx.report(self.name, "failed", str(exc))
            raise

        for pos in anfrage.positionen:
            log.info(
                "  Pos %d [%s]: %s x%s - %s",
                pos.pos_nr,
                pos.confidence,
                pos.artikelnummer,
                pos.menge,
                pos.bezeichnung[:50],
            )

        ctx.persist("extracted", anfrage.model_dump(mode="json"))
        ctx.report(self.name, "completed", f"{len(anfrage.positionen)} Positionen")
        return anfrage
