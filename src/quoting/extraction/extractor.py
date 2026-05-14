"""Extraction: attachments + mail body -> validated Anfrage."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..core import Anfrage, Settings, get_logger, load_settings
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
from .prompts import build_prompt_parts

log = get_logger()


class ExtractionError(RuntimeError):
    """Raised when extraction fails with a human-readable reason."""


def extract_anfrage(
    attachments: list[Path],
    mail_body: str = "",
    settings: Settings | None = None,
    own_party_context: OwnPartyContext | None = None,
) -> tuple[Anfrage, TokenUsage | None]:
    """Run LLM extraction and return a validated Anfrage plus token usage."""
    settings = settings or load_settings()
    own_party_context = own_party_context or load_own_party_context()
    llm = build_llm(settings)

    doc_sections, images = load_attachments(attachments, dpi=settings.pdf_render_dpi)
    schema_json = json.dumps(Anfrage.model_json_schema(), indent=2, ensure_ascii=False)
    stable_prefix, variable_suffix = build_prompt_parts(
        schema_json,
        mail_body,
        doc_sections,
        format_own_party_prompt_context(own_party_context),
    )

    log.info("Calling LLM (%s) with %d image(s), stable=%d chars, variable=%d chars",
             settings.llm_provider, len(images), len(stable_prefix), len(variable_suffix))

    try:
        llm_response = with_retry(
            llm.generate,
            prompt=variable_suffix,
            images=images,
            cacheable_prefix=stable_prefix,
            max_retries=settings.llm_max_retries,
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

    sanitize_own_customer_fields(anfrage, own_party_context)

    if llm_response.usage:
        log.info("Extraction OK: %d position(s), tokens in=%d out=%d",
                 len(anfrage.positionen), llm_response.usage.input_tokens,
                 llm_response.usage.output_tokens)
    else:
        log.info("Extraction OK: %d position(s)", len(anfrage.positionen))
    return anfrage, llm_response.usage
