"""GET /metrics — aggregate dashboard metrics."""

from __future__ import annotations

from fastapi import APIRouter

from quoting.api import _common
from quoting.api.services.metrics_service import compute_metrics

router = APIRouter()


@router.get("/metrics")
def get_metrics() -> dict:
    return compute_metrics(_common.REVIEW_DIR)
