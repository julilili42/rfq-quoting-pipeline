"""Verify GeminiClient request wiring with a mocked SDK client."""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from quoting.core import Settings
from quoting.extraction.llm.gemini import GeminiClient


@dataclass
class _FakeUsage:
    prompt_token_count: int = 100
    candidates_token_count: int = 50
    total_token_count: int = 150


@dataclass
class _FakeResponse:
    text: str = '{"positionen": []}'
    usage_metadata: _FakeUsage = field(default_factory=_FakeUsage)


def _make_client(
    *,
    thinking_budget: int = 0,
) -> tuple[GeminiClient, MagicMock]:
    """Construct a GeminiClient where genai.Client is fully mocked."""
    settings = Settings(
        google_api_key="fake-key",
        gemini_model="gemini-2.5-flash-lite",
        gemini_thinking_budget=thinking_budget,
    )
    fake_genai_client = MagicMock()
    fake_genai_client.models.generate_content.return_value = _FakeResponse()

    import google.genai

    original = google.genai.Client
    google.genai.Client = MagicMock(return_value=fake_genai_client)
    try:
        client = GeminiClient(settings)
    finally:
        google.genai.Client = original
    return client, fake_genai_client.models.generate_content


def test_prompt_is_sent_as_first_content_item():
    client, gen_call = _make_client()

    client.generate(prompt="JUST MAIL")

    assert gen_call.call_args.kwargs["contents"][0] == "JUST MAIL"


def test_thinking_budget_is_set_when_configured():
    client, gen_call = _make_client(thinking_budget=0)

    client.generate(prompt="MAIL")

    cfg = gen_call.call_args.kwargs["config"]
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0


def test_negative_thinking_budget_omits_generate_config():
    client, gen_call = _make_client(thinking_budget=-1)

    client.generate(prompt="MAIL")

    assert gen_call.call_args.kwargs["config"] is None


def test_usage_metadata_is_mapped_to_token_usage():
    client, _ = _make_client()

    response = client.generate(prompt="MAIL")

    assert response.text == '{"positionen": []}'
    assert response.usage is not None
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 50
    assert response.usage.total_tokens == 150
