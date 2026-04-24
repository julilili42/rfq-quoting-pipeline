"""Abstract LLM client + retry helper."""
from __future__ import annotations

import time
from typing import Any, Protocol

from ...core import get_logger

log = get_logger()


class LLMClient(Protocol):
    """Minimal interface every provider must implement."""

    def generate(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None = None,
    ) -> str: ...


def with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.5,
    **kwargs,
):
    """Exponential backoff for transient LLM failures."""
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
    assert last_exc is not None
    raise last_exc
