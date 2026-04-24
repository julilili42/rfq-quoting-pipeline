"""Gemini client (google-genai SDK)."""
from __future__ import annotations

from typing import Any

from ...core import Settings
from .base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings):
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY missing in environment")

        from google import genai

        self._client = genai.Client(api_key=settings.google_api_key)
        self._model = settings.gemini_model

    def generate(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        from google.genai import types

        contents: list[Any] = [prompt]
        if images:
            for img in images:
                contents.append(types.Part.from_bytes(
                    data=img["data"],
                    mime_type=img["mime_type"],
                ))

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
        )
        return response.text or ""
