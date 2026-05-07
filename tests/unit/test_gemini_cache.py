"""Verify GeminiClient context-cache wiring with a mocked SDK client."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from quoting.core import Settings
from quoting.extraction.llm.gemini import GeminiClient, _hash_prefix


@dataclass
class _FakeUsage:
    prompt_token_count: int = 100
    candidates_token_count: int = 50
    total_token_count: int = 150
    cached_content_token_count: int = 0


@dataclass
class _FakeResponse:
    text: str = '{"positionen": []}'
    usage_metadata: _FakeUsage = field(default_factory=_FakeUsage)


@dataclass
class _FakeCache:
    name: str = "cachedContents/test-cache-123"


def _make_client(*, cache_enabled: bool = True, ttl_s: int = 3600) -> tuple[GeminiClient, MagicMock, MagicMock]:
    """Construct a GeminiClient where genai.Client is fully mocked."""
    settings = Settings(
        google_api_key="fake-key",
        gemini_model="gemini-2.5-flash-lite",
        gemini_thinking_budget=0,
        gemini_cache_enabled=cache_enabled,
        gemini_cache_ttl_s=ttl_s,
    )
    fake_genai_client = MagicMock()
    fake_genai_client.caches.create.return_value = _FakeCache()
    fake_genai_client.models.generate_content.return_value = _FakeResponse()

    # Patch the genai.Client constructor inside __init__.
    import google.genai
    original = google.genai.Client
    google.genai.Client = MagicMock(return_value=fake_genai_client)
    try:
        client = GeminiClient(settings)
    finally:
        google.genai.Client = original
    return client, fake_genai_client.caches.create, fake_genai_client.models.generate_content


# ---------------------------------------------------------------- helpers

LONG_PREFIX = "STABLE PREFIX" * 500  # ~6500 chars > _CACHE_MIN_CHARS
SHORT_PREFIX = "tiny"


# --------------------------------------------------------------- tests

def test_cache_created_on_first_call_with_long_prefix():
    client, create_call, gen_call = _make_client()

    client.generate(prompt="MAIL", cacheable_prefix=LONG_PREFIX)

    assert create_call.call_count == 1
    # generate_content config carries the cache name
    call_kwargs = gen_call.call_args.kwargs
    assert call_kwargs["config"].cached_content == "cachedContents/test-cache-123"
    # contents send only the variable part (no prefix concat)
    assert call_kwargs["contents"][0] == "MAIL"


def test_cache_reused_across_calls_with_same_prefix():
    client, create_call, gen_call = _make_client()

    client.generate(prompt="MAIL 1", cacheable_prefix=LONG_PREFIX)
    client.generate(prompt="MAIL 2", cacheable_prefix=LONG_PREFIX)
    client.generate(prompt="MAIL 3", cacheable_prefix=LONG_PREFIX)

    # Cache built once, reused twice.
    assert create_call.call_count == 1
    assert gen_call.call_count == 3
    # All three reference the same cache.
    for call in gen_call.call_args_list:
        assert call.kwargs["config"].cached_content == "cachedContents/test-cache-123"


def test_cache_rebuilt_when_prefix_content_changes():
    client, create_call, _ = _make_client()

    client.generate(prompt="A", cacheable_prefix=LONG_PREFIX)
    client.generate(prompt="B", cacheable_prefix="DIFFERENT" * 1000)

    assert create_call.call_count == 2


def test_short_prefix_skips_caching():
    client, create_call, gen_call = _make_client()

    client.generate(prompt="MAIL", cacheable_prefix=SHORT_PREFIX)

    assert create_call.call_count == 0
    # contents include the prefix concatenated (since no cache)
    call_kwargs = gen_call.call_args.kwargs
    assert SHORT_PREFIX in call_kwargs["contents"][0]
    assert "MAIL" in call_kwargs["contents"][0]


def test_disabled_cache_skips_caching():
    client, create_call, gen_call = _make_client(cache_enabled=False)

    client.generate(prompt="MAIL", cacheable_prefix=LONG_PREFIX)

    assert create_call.call_count == 0
    # Prefix is concatenated inline.
    call_kwargs = gen_call.call_args.kwargs
    assert LONG_PREFIX[:30] in call_kwargs["contents"][0]


def test_cache_creation_failure_disables_for_process():
    client, create_call, gen_call = _make_client()
    create_call.side_effect = RuntimeError("quota exceeded")

    # First call: cache creation fails, falls back to inline concat.
    client.generate(prompt="MAIL 1", cacheable_prefix=LONG_PREFIX)
    # Second call: should not retry the cache (disabled for process).
    client.generate(prompt="MAIL 2", cacheable_prefix=LONG_PREFIX)

    assert create_call.call_count == 1  # not retried
    # Both generate calls succeed via inline concat.
    assert gen_call.call_count == 2
    for call in gen_call.call_args_list:
        kw = call.kwargs
        # No cached_content in config when cache is disabled.
        cfg = kw.get("config")
        assert cfg is None or getattr(cfg, "cached_content", None) is None


def test_cache_reference_error_falls_back_and_retries_inline():
    """If the model rejects a cached_content (TTL bug etc), fall back."""
    client, create_call, gen_call = _make_client()

    # First generate raises a cache-error, second (without cache) succeeds.
    gen_call.side_effect = [
        RuntimeError("cached_content not found"),
        _FakeResponse(),
    ]

    response = client.generate(prompt="MAIL", cacheable_prefix=LONG_PREFIX)

    # The retry happened.
    assert gen_call.call_count == 2
    # First call had cache, second didn't.
    first_cfg = gen_call.call_args_list[0].kwargs["config"]
    second_cfg = gen_call.call_args_list[1].kwargs.get("config")
    assert first_cfg.cached_content == "cachedContents/test-cache-123"
    assert second_cfg is None or getattr(second_cfg, "cached_content", None) is None
    # Got the response from the retry.
    assert response.text == '{"positionen": []}'


def test_hash_prefix_is_stable():
    a = _hash_prefix(LONG_PREFIX)
    b = _hash_prefix(LONG_PREFIX)
    c = _hash_prefix(LONG_PREFIX + "x")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_no_cacheable_prefix_passes_prompt_through():
    client, create_call, gen_call = _make_client()

    client.generate(prompt="JUST MAIL")

    assert create_call.call_count == 0
    assert gen_call.call_args.kwargs["contents"][0] == "JUST MAIL"


def test_thinking_budget_still_set_when_caching():
    """Caching shouldn't drop the thinking_budget=0 we set in step 1."""
    client, _, gen_call = _make_client()

    client.generate(prompt="MAIL", cacheable_prefix=LONG_PREFIX)

    cfg = gen_call.call_args.kwargs["config"]
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0
