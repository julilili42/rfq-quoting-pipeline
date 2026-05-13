from __future__ import annotations

from quoting.api import frontend_router
from quoting.extraction.llm.base import LLMResponse, TokenUsage


class _OkClient:
    def generate(self, *args, **kwargs):
        return LLMResponse(
            text='{"status":"ok"}',
            usage=TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10),
        )


class _FailingClient:
    def __init__(self, message: str):
        self._message = message

    def generate(self, *args, **kwargs):
        raise RuntimeError(self._message)


def test_probe_llm_provider_returns_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr(
        "quoting.extraction.llm.build_llm",
        lambda settings: _OkClient(),
    )

    result = frontend_router.probe_llm_provider()

    assert result.status == "ok"
    assert result.provider == "gemini"
    assert result.response_preview == '{"status":"ok"}'
    assert result.usage is not None
    assert result.usage.total_tokens == 10


def test_probe_llm_provider_returns_scrubbed_error(monkeypatch):
    secret = "test-google-key"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    monkeypatch.setattr(
        "quoting.extraction.llm.build_llm",
        lambda settings: _FailingClient(f"provider rejected key {secret}"),
    )

    result = frontend_router.probe_llm_provider()

    assert result.status == "error"
    assert result.error_type == "RuntimeError"
    assert secret not in result.detail
    assert "***" in result.detail
