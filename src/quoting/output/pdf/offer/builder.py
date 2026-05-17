"""PDF builder orchestration."""
from __future__ import annotations

from pathlib import Path

from ....core import Anfrage
from ....pricing import Quotation
from .canvas import OfferTemplateCanvas
from .config import OfferPdfConfig
from .flowables import build_story
from .formatting import find_logo_path


def build_offer_pdf(
    anfrage: Anfrage,
    quotation: Quotation,
    path: Path,
    config: OfferPdfConfig | None = None,
) -> None:
    """Build the prototype offer PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    config = config or OfferPdfConfig()
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.55 * cm,
        rightMargin=1.55 * cm,
        topMargin=7.0 * cm,
        bottomMargin=1.65 * cm,
        title=f"Angebot Entwurf {quotation.belegnummer or ''}",
        author=config.company_name,
    )

    story = build_story(
        anfrage=anfrage,
        quotation=quotation,
        doc_width=doc.width,
        config=config,
    )

    logo_path = find_logo_path(config)
    canvas_cls = OfferTemplateCanvas.create_canvas_class(
        config=config,
        quotation=quotation,
        logo_path=logo_path,
    )

    doc.build(story, canvasmaker=canvas_cls)
