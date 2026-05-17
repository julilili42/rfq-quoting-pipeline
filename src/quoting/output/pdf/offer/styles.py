"""ReportLab paragraph styles for the prototype offer PDF."""
from __future__ import annotations

from typing import Any


def build_styles() -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()

    return {
        "body": ParagraphStyle(
            "OfferBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=11.2,
            textColor=colors.black,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "OfferSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.7,
            leading=9.4,
            textColor=colors.black,
            spaceAfter=3,
        ),
        "sender": ParagraphStyle(
            "OfferSender",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=5.9,
            leading=7.1,
            textColor=colors.black,
            spaceAfter=10,
        ),
        "address": ParagraphStyle(
            "OfferAddress",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.4,
            textColor=colors.black,
            spaceAfter=0,
        ),
        "notice": ParagraphStyle(
            "OfferNotice",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.5,
            textColor=colors.HexColor("#E30613"),
            spaceAfter=0,
        ),
        "section_heading": ParagraphStyle(
            "OfferSectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.0,
            leading=11.0,
            textColor=colors.black,
            spaceBefore=3,
            spaceAfter=5,
        ),
        "table": ParagraphStyle(
            "OfferTable",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=9.8,
            textColor=colors.black,
        ),
        "table_small": ParagraphStyle(
            "OfferTableSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=9.2,
            textColor=colors.black,
        ),
    }
