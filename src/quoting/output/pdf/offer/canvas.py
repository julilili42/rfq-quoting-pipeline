"""Static header/footer canvas for offer PDFs."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ....pricing import Quotation
from ..offer.config import OfferPdfConfig
from ..offer.formatting import html_escape


class OfferTemplateCanvas:
    """Factory wrapper for a ReportLab canvas with page count support."""

    @staticmethod
    def create_canvas_class(config: OfferPdfConfig, quotation: Quotation, logo_path: Path | None):
        from reportlab.pdfgen import canvas as pdf_canvas

        class _Canvas(pdf_canvas.Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states: list[dict[str, Any]] = []

            def showPage(self):  # noqa: N802 - ReportLab API
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):  # noqa: D401 - ReportLab API
                page_count = len(self._saved_page_states)

                for page_num, state in enumerate(self._saved_page_states, start=1):
                    self.__dict__.update(state)
                    draw_header_footer(
                        c=self,
                        config=config,
                        quotation=quotation,
                        logo_path=logo_path,
                        page_num=page_num,
                        page_count=page_count,
                    )
                    super().showPage()

                super().save()

        return _Canvas


def draw_header_footer(
    c,
    config: OfferPdfConfig,
    quotation: Quotation,
    logo_path: Path | None,
    page_num: int,
    page_count: int,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4

    width, height = A4
    red = colors.HexColor("#E30613")
    blue = colors.HexColor("#005AA9")

    c.saveState()

    _draw_logo(c, logo_path, width, height)
    _draw_brand_rule(c, red, blue, width, height)
    _draw_offer_header(c, config, quotation, page_num, page_count, height)
    _draw_footer(c, config)

    c.restoreState()


def _draw_logo(c, logo_path: Path | None, width: float, height: float) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader

    if logo_path and logo_path.exists():
        try:
            img = ImageReader(str(logo_path))
            img_w, img_h = img.getSize()
            target_w = 4.9 * cm
            target_h = target_w * img_h / img_w

            c.drawImage(
                img,
                (width - target_w) / 2,
                height - 2.3 * cm,
                width=target_w,
                height=target_h,
                preserveAspectRatio=True,
                mask="auto",
            )
            return
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Logo load failed (%s): %s", logo_path, exc)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 1.45 * cm, "[LOGO]")


def _draw_brand_rule(c, red, blue, width: float, height: float) -> None:
    from reportlab.lib.units import cm

    y_line = height - 2.55 * cm

    c.setLineWidth(3)
    c.setStrokeColor(red)
    c.line(1.3 * cm, y_line, width / 2, y_line)

    c.setStrokeColor(blue)
    c.line(width / 2, y_line, width - 1.3 * cm, y_line)


def _draw_offer_header(
    c,
    config: OfferPdfConfig,
    quotation: Quotation,
    page_num: int,
    page_count: int,
    height: float,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    document_no = quotation.belegnummer or config.document_no_fallback

    x_label = 12.25 * cm
    x_value = 15.15 * cm
    y = height - 3.45 * cm

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_label, y, "Angebot")

    y -= 0.55 * cm
    c.setFont("Helvetica", 8.5)
    c.drawString(x_label, y, f"Seite {page_num} von {page_count}")

    y -= 0.45 * cm

    customer_no = (
        getattr(quotation, "kundennummer", None)
        or config.customer_no_fallback
    )

    rows = [
        ("Datum:", datetime.now().strftime("%d.%m.%Y")),
        ("Beleg-Nr.:", document_no),
        ("Kunden-Nr.:", customer_no),
    ]

    if page_num == 1:
        rows.extend([
            ("Kontaktperson:", config.contact_person),
            ("Telefon:", config.contact_phone),
            ("E-Mail:", config.contact_email),
        ])

    c.setFont("Helvetica", 8.0)
    for label, value in rows:
        c.drawString(x_label, y, label)
        c.drawString(x_value, y, html_escape(value).replace("<br/>", " "))
        y -= 0.32 * cm


def _draw_footer(c, config: OfferPdfConfig) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 5.2)

    footer_y = 0.55 * cm

    _draw_multiline(c, 1.35 * cm, footer_y, list(config.footer_left), leading=6.0)
    _draw_multiline(c, 9.8 * cm, footer_y, list(config.footer_bank), leading=6.0)
    _draw_multiline(c, 13.55 * cm, footer_y, list(config.footer_iban), leading=6.0)
    _draw_multiline(c, 17.35 * cm, footer_y, list(config.footer_bic), leading=6.0)


def _draw_multiline(c, x: float, y: float, lines: list[str], leading: float) -> None:
    for i, line in enumerate(reversed(lines)):
        c.drawString(x, y + i * leading, line)
