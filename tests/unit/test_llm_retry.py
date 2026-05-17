"""Tests for quoting.extraction.llm.base.with_retry."""
from __future__ import annotations

import pytest

from quoting.extraction.llm.base import with_retry


def test_retry_succeeds_on_first_attempt():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = with_retry(fn, max_retries=3, base_delay=0)
    assert result == "ok"
    assert len(calls) == 1


def test_retry_succeeds_after_failures():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "done"

    result = with_retry(fn, max_retries=5, base_delay=0)
    assert result == "done"
    assert len(calls) == 3


def test_retry_raises_after_max_retries():
    def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        with_retry(fn, max_retries=2, base_delay=0)


def test_retry_raises_on_max_retries_zero():
    def fn():
        return "x"

    with pytest.raises(ValueError, match="max_retries must be >= 1"):
        with_retry(fn, max_retries=0)


def test_retry_passes_args_and_kwargs():
    def fn(a, b, *, c):
        return a + b + c

    result = with_retry(fn, 1, 2, max_retries=1, base_delay=0, c=3)
    assert result == 6


def test_retry_attempt_count_equals_max_on_failure():
    calls = []

    def fn():
        calls.append(1)
        raise OSError("boom")

    with pytest.raises(IOError):
        with_retry(fn, max_retries=4, base_delay=0)

    assert len(calls) == 4
