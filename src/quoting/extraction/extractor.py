"""Extraction: attachments + mail body -> validated Anfrage."""
from __future__ import annotations

import json
from pathlib import Path

from ..core import Anfrage, Settings, get_logger, load_settings
from .document_loader import load_attachments
from .json_utils import extract_json_object
from .llm import build_llm, with_retry
from .prompts import build_prompt

log = get_logger()


def extract_anfrage(
    attachments: list[Path],
    mail_body: str = "",
    settings: Settings | None = None,
) -> Anfrage:
    """Run LLM extraction and return a validated Anfrage."""
    settings = settings or load_settings()
    llm = build_llm(settings)

    doc_sections, images = load_attachments(attachments, dpi=settings.pdf_render_dpi)
    schema_json = json.dumps(Anfrage.model_json_schema(), indent=2, ensure_ascii=False)
    prompt = build_prompt(schema_json, mail_body, doc_sections)

    log.info("Calling LLM (%s) with %d image(s), prompt=%d chars",
             settings.llm_provider, len(images), len(prompt))

    raw = with_retry(
        llm.generate,
        prompt=prompt,
        images=images,
        max_retries=settings.llm_max_retries,
    )
    raw_json = extract_json_object(raw)
    anfrage = Anfrage.model_validate_json(raw_json)
    log.info("Extraction OK: %d position(s)", len(anfrage.positionen))
    return anfrage
