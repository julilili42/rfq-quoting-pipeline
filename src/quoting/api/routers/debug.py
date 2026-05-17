"""GET /debug and POST /debug/llm — health checks and live provider probe."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from quoting.api import _common
from quoting.api.services.debug_service import (
    DebugInfo,
    LlmProbeResult,
    compute_debug_info,
    probe_llm,
)

router = APIRouter()


@router.get("/debug", response_model=DebugInfo)
def get_debug_info() -> DebugInfo:
    return compute_debug_info(_common.PROJECT_ROOT)


@router.post("/debug/llm", response_model=LlmProbeResult)
def probe_llm_provider(
    timeout_s: Annotated[int, Query(ge=1, le=120)] = 20,
) -> LlmProbeResult:
    """Run an explicit, minimal provider call for the debug page.

    The regular ``/debug`` endpoint only validates configuration. This
    endpoint intentionally performs a real LLM request, so the UI calls it
    only after a user action.
    """
    return probe_llm(timeout_s)
