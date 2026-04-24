"""Factory: settings in, LLMClient out."""
from __future__ import annotations

from ...core import Settings
from .base import LLMClient


def build_llm(settings: Settings) -> LLMClient:
    """Instantiate the provider configured in settings."""
    if settings.llm_provider == "gemini":
        from .gemini import GeminiClient
        return GeminiClient(settings)
    if settings.llm_provider == "azure":
        from .azure import AzureClient
        return AzureClient(settings)
    raise ValueError(f"Unknown provider: {settings.llm_provider}")
