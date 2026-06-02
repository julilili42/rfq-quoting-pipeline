"""Extraction: attachments + mail body -> validated Anfrage."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from ..core import Anfrage, Settings, get_logger, load_settings
from .candidates import build_candidate_hints
from .document_loader import load_attachments
from .json_utils import extract_json_object
from .llm import build_llm, with_retry
from .llm.base import TokenUsage
from .own_party import (
    OwnPartyContext,
    format_own_party_prompt_context,
    load_own_party_context,
    sanitize_own_customer_fields,
)
from .prompts import build_prompt
from .source_guard import harden_extraction_with_sources

log = get_logger()


class ExtractionError(RuntimeError):
    """Raised when extraction fails with a human-readable reason."""


def extract_anfrage(
    attachments: list[Path],
    mail_body: str = "",
    settings: Settings | None = None,
    own_party_context: OwnPartyContext | None = None,
    on_llm_retry: Callable[[dict], None] | None = None,
) -> tuple[Anfrage, TokenUsage | None]:
    """Run LLM extraction and return a validated Anfrage plus token usage."""
    settings = settings or load_settings()
    own_party_context = own_party_context or load_own_party_context()
    llm = build_llm(settings)

    doc_sections, images = load_attachments(attachments, dpi=settings.pdf_render_dpi)
    schema_json = json.dumps(Anfrage.model_json_schema(), indent=2, ensure_ascii=False)
    candidate_hints = build_candidate_hints(mail_body, doc_sections)
    prompt = build_prompt(
        schema_json,
        mail_body,
        doc_sections,
        format_own_party_prompt_context(own_party_context),
        candidate_hints,
    )

    log.info("Calling LLM (%s) with %d image(s), prompt=%d chars",
             settings.llm_provider, len(images), len(prompt))

    try:
        llm_response = with_retry(
            llm.generate,
            prompt=prompt,
            images=images,
            max_retries=settings.llm_max_retries,
            on_retry=(
                lambda **event: on_llm_retry(
                    {
                        "provider": settings.llm_provider,
                        **event,
                    },
                )
            )
            if on_llm_retry is not None
            else None,
        )
    except Exception as exc:
        raise ExtractionError(f"LLM call failed: {exc}") from exc

    try:
        raw_json = extract_json_object(llm_response.text)
    except ValueError as exc:
        raise ExtractionError(f"LLM returned no parseable JSON: {exc}") from exc

    try:
        anfrage = Anfrage.model_validate_json(raw_json)
    except ValidationError as exc:
        raise ExtractionError(f"LLM output does not match Anfrage schema: {exc}") from exc

    source_guard_changes = harden_extraction_with_sources(anfrage, mail_body, doc_sections)
    if source_guard_changes:
        log.info("Extraction source guard adjusted: %s", ", ".join(source_guard_changes))

    sanitize_own_customer_fields(anfrage, own_party_context)

    if llm_response.usage:
        log.info("Extraction OK: %d position(s), tokens in=%d out=%d",
                 len(anfrage.positionen), llm_response.usage.input_tokens,
                 llm_response.usage.output_tokens)
    else:
        log.info("Extraction OK: %d position(s)", len(anfrage.positionen))
    return anfrage, llm_response.usage
