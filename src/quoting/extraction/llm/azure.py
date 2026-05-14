"""Azure OpenAI (Nexus) client."""
from __future__ import annotations

import base64
from typing import Any

from ...core import Settings
from .base import LLMClient, LLMResponse, TokenUsage


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
        *,
        cacheable_prefix: str | None = None,
    ) -> LLMResponse:
        # Azure has its own implicit caching for repeated prefixes; we
        # just concatenate so the model sees the same final prompt either
        # way. Explicit caching support can be added later.
        if cacheable_prefix:
            prompt = f"{cacheable_prefix}\n\n{prompt}" if prompt else cacheable_prefix
        parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if images:
            for img in images:
                if label := img.get("label"):
                    parts.append({"type": "text", "text": label})
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

        usage = None
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = TokenUsage(
                input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                output_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )

        if not resp.choices:
            raise RuntimeError(
                f"Azure returned no choices (model={self._model}). "
                "Check API response for rate-limit or content-filter errors."
            )
        return LLMResponse(text=resp.choices[0].message.content or "", usage=usage)
