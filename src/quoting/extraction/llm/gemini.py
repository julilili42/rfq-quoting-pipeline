"""Gemini client (google-genai SDK)."""
from __future__ import annotations

import logging
from typing import Any

from ...core import Settings
from .base import LLMClient, LLMResponse, TokenUsage

log = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings):
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY missing in environment")

        from google import genai

        self._client = genai.Client(api_key=settings.google_api_key)
        self._model = settings.gemini_model
        self._thinking_budget = settings.gemini_thinking_budget

    def generate(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None = None,
        *,
        cacheable_prefix: str | None = None,
    ) -> LLMResponse:
        from google.genai import types

        if cacheable_prefix:
            prompt = f"{cacheable_prefix}\n\n{prompt}" if prompt else cacheable_prefix

        contents: list[Any] = [prompt]
        if images:
            for img in images:
                contents.append(types.Part.from_bytes(
                    data=img["data"],
                    mime_type=img["mime_type"],
                ))

        config_kwargs: dict[str, Any] = {}
        if self._thinking_budget >= 0:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._thinking_budget,
            )
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        usage = None
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = TokenUsage(
                input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
                output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
                total_tokens=getattr(meta, "total_token_count", 0) or 0,
            )

        return LLMResponse(text=response.text or "", usage=usage)
