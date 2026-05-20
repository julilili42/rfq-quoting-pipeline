"""Aggregator for the React frontend's HTTP surface.

The actual handlers live in :mod:`quoting.api.routers`. Shared globals
(``REVIEW_DIR``, the cached pipeline, helpers) live in
:mod:`quoting.api._common`. Pure business logic lives in
:mod:`quoting.api.services`.

This module exists to preserve the public surface (``router`` plus the
helpers/models that external callers and tests import directly).

Wire-up in ``quoting/api/review_api.py``:

    from quoting.api.frontend_router import router as frontend_router
    app.include_router(frontend_router)
"""

from __future__ import annotations

from fastapi import APIRouter

from quoting.api import _common
from quoting.api.routers import (
    attachments as _attachments_router,
)
from quoting.api.routers import (
    debug as _debug_router,
)
from quoting.api.routers import (
    metrics as _metrics_router,
)
from quoting.api.routers import (
    reviews as _reviews_router,
)
from quoting.api.routers import (
    stammdaten as _stammdaten_router,
)
from quoting.api.routers import (
    upload as _upload_router,
)
from quoting.api.routers.debug import probe_llm_provider  # noqa: F401  (re-export)
from quoting.api.routers.stammdaten import (  # noqa: F401  (re-export)
    CustomArticleRequest,
    create_custom_article_match,
)
from quoting.api.services.debug_service import (
    recent_pipeline_failures as _recent_pipeline_failures,  # noqa: F401  (re-export)
)
from quoting.api.services.debug_service import (
    stammdaten_quality as _stammdaten_quality,  # noqa: F401  (re-export)
)
from quoting.api.services.quotation_service import (
    filter_redundant_custom_price_overrides as _filter_redundant_custom_price_overrides,  # noqa: F401
)
from quoting.api.services.quotation_service import (
    remove_position_price_overrides as _remove_position_price_overrides,  # noqa: F401
)
from quoting.api.services.review_service import (
    enrich_exact_article_edits as _enrich_exact_article_edits,  # noqa: F401  (re-export)
)
from quoting.api.services.review_service import (
    load_or_recompute_matches as _load_or_recompute_matches,  # noqa: F401  (re-export)
)

REVIEW_DIR = _common.REVIEW_DIR
_pipeline = _common._pipeline  # noqa: SLF001
_get_pipeline = _common.get_pipeline


router = APIRouter(prefix="/api", tags=["frontend"])
router.include_router(_metrics_router.router)
router.include_router(_reviews_router.router)
router.include_router(_attachments_router.router)
router.include_router(_upload_router.router)
router.include_router(_stammdaten_router.router)
router.include_router(_debug_router.router)
