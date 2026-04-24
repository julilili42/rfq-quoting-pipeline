"""Azure OpenAI (Nexus) client."""
from __future__ import annotations

import base64
from typing import Any

from ...core import Settings
from .base import LLMClient


class AzureClient(LLMClient):
    def __init__(self, settings: Settings):
        if not settings.nexus_api_key:
            raise ValueError("NEXUS_API_KEY missing in environment")

        import openai

        self._client = openai.AzureOpenAI(
            api_version=settings.azure_api_version,
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.nexus_api_key,
            timeout=settings.llm_timeout_s,
        )
        self._model = settings.azure_model

    def generate(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if images:
            for img in images:
                b64 = base64.b64encode(img["data"]).decode()
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img['mime_type']};base64,{b64}",
                        "detail": "high",
                    },
                })
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": parts}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""
