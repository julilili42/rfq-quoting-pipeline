"""Public PDF export entry point.

Keeps the old import path stable:

    from quoting.output import build_draft_pdf
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core import Anfrage, get_logger
from ...pricing import Quotation
from ..json_writer import save_json

log = get_logger()


def build_draft_pdf(
    anfrage: Anfrage,
    quotation: Quotation,
    path: Path,
    *,
    is_final: bool = False,
    company_profile: Any | None = None,
) -> None:
    """Generate a quotation PDF.

    Parameters
    ----------
    is_final
        If True, suppress the red AI-warning banner. Used when the
        review has been explicitly approved.
    company_profile
        Optional ``CompanyProfile`` from settings_store (or a
        per-review override produced by the editor). When provided,
        sender/contact information from this profile is baked into
        the PDF instead of the placeholder defaults.

    Falls back to JSON if ReportLab is not installed.
    """
    try:
        import reportlab  # noqa: F401
    except ImportError:
        log.warning("reportlab not installed - writing JSON instead of PDF")
        save_json(quotation.to_dict(), path.with_suffix(".json"))
        return

    from .offer import build_offer_pdf
    from .offer.config import OfferPdfConfig, config_from_company_profile

    if company_profile is not None:
        config = config_from_company_profile(company_profile, is_final=is_final)
    else:
        config = OfferPdfConfig(is_final=is_final)

    customer_no = (getattr(anfrage, "kundennummer", None) or "").strip()
    if customer_no:
        config = config.with_overrides(customer_no_fallback=customer_no)

    build_offer_pdf(
        anfrage=anfrage,
        quotation=quotation,
        path=path,
        config=config,
    )
