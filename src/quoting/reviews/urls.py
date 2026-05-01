"""URL helpers shared by the API server and the Streamlit UI.

The Streamlit UI is a separate process from the FastAPI server. To
embed PDFs in the UI without re-implementing the file-serving logic on
the Streamlit side, the UI iframe-loads them straight from the API
using the URLs assembled here.

Resolution order for the API base URL:

1. ``.tunnel_url`` file at the project root — written by ngrok / cloudflared
   wrappers when the API is exposed via a tunnel.
2. ``API_BASE_URL`` environment variable.
3. Default ``http://127.0.0.1:8000``.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import quote


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TUNNEL_FILE = _PROJECT_ROOT / ".tunnel_url"


def api_base_url() -> str:
    """Return the public base URL for the review API, no trailing slash."""
    try:
        if _TUNNEL_FILE.exists():
            url = _TUNNEL_FILE.read_text(encoding="utf-8").strip()
            if url:
                return url.rstrip("/")
    except Exception:
        pass
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def pdf_url(
    review_id: str,
    *,
    kind: str = "current",
    cache_bust: bool = True,
) -> str:
    """Build the URL the iframe should load for a given review's PDF.

    ``kind`` is one of ``"draft"``, ``"final"`` or ``"current"`` —
    matching the API's three PDF endpoints. The cache-buster query
    parameter prevents the browser from showing a stale render after
    the user rebuilds the PDF.
    """
    base = api_base_url()
    safe_id = quote(review_id, safe="")
    if kind == "draft":
        path = f"/api/reviews/{safe_id}/pdf/draft"
    elif kind == "final":
        path = f"/api/reviews/{safe_id}/pdf/final"
    else:
        path = f"/api/reviews/{safe_id}/pdf"
    url = f"{base}{path}"
    if cache_bust:
        url += f"?v={int(time.time() * 1000)}"
    return url
