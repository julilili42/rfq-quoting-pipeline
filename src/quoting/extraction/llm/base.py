"""Abstract LLM client + retry helper."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from ...core import get_logger

log = get_logger()


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    text: str
    usage: TokenUsage | None


class LLMClient(Protocol):
    """Minimal interface every provider must implement."""

    def generate(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None = None,
        *,
        cacheable_prefix: str | None = None,
    ) -> LLMResponse:
        """Run extraction. ``prompt`` is the variable, per-RFQ content.

        Image dicts may carry an optional ``label``. Providers should send
        that label directly before the corresponding image part so the model
        can map vision evidence back to source files/pages.

        ``cacheable_prefix`` (optional): a stable prompt prefix that the
        provider may cache across calls (Gemini context caching). When
        provided, ``prompt`` is treated as the suffix; the provider
        guarantees the model sees ``cacheable_prefix + prompt`` either way.
        Providers that don't support caching simply concatenate.
        """


def with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.5,
    **kwargs,
):
    """Exponential backoff for transient LLM failures."""
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - providers raise many types
            last_exc = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning("LLM call failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt, max_retries, exc, delay)
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]  # guaranteed non-None: loop ran >= 1 time
