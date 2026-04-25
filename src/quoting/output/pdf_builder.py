"""Draft-quotation PDF builder (reportlab)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import Anfrage, get_logger
from ..pricing import Quotation
from .json_writer import save_json

log = get_logger()


def build_draft_pdf(
    anfrage: Anfrage,
    quotation: Quotation,
    path: Path,
) -> None:
    """Generate the DRAFT quotation PDF."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        log.warning("reportlab not installed - writing JSON instead of PDF")
        save_json(quotation.to_dict(), path.with_suffix(".json"))
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Draft Quotation {quotation.belegnummer or ''}",
    )

    styles = getSampleStyleSheet()
    draft_style = ParagraphStyle(
        "Draft", parent=styles["Heading1"],
        textColor=colors.red, alignment=1, fontSize=20,
    )
    story: list[Any] = []

    # Header
    story.append(Paragraph("DRAFT - INTERNAL REVIEW ONLY", draft_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Angebot (Entwurf)", styles["Title"]))
    story.append(Paragraph(
        f"Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # Customer
    story.append(Paragraph(_customer_html(quotation), styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    # Line items
    story.append(Paragraph("Positionen", styles["Heading2"]))
    story.append(_items_table(quotation, styles, colors))
    story.append(Spacer(1, 0.5 * cm))

    # Terms
    story.append(Paragraph("Konditionen", styles["Heading2"]))
    story.append(Paragraph(
        f"<b>Incoterms:</b> {quotation.incoterms or '—'}<br/>"
        f"<b>Zahlungsbedingungen:</b> {quotation.zahlungsbedingungen or '—'}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # Warnings
    if quotation.warnungen:
        story.append(Paragraph("⚠️ Hinweise zur Freigabe", styles["Heading2"]))
        for w in quotation.warnungen:
            story.append(Paragraph(f"• {w}", styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

    if anfrage.unsicherheiten:
        story.append(Paragraph("🔍 Unsicherheiten aus der Extraktion", styles["Heading2"]))
        for u in anfrage.unsicherheiten:
            story.append(Paragraph(f"• {u}", styles["Normal"]))

    # Audit page
    story.append(PageBreak())
    story.append(Paragraph("Audit-Protokoll (Extraktion)", styles["Heading2"]))
    for pos in anfrage.positionen:
        story.append(Paragraph(
            f"<b>Pos {pos.pos_nr}</b> (Confidence: {pos.confidence})<br/>"
            f'<i>Quelle:</i> "{pos.source_quote}"',
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _customer_html(q: Quotation) -> str:
    return (
        f"<b>Kunde:</b> {q.kunde_firma or '—'}<br/>"
        f"<b>Ansprechpartner:</b> {q.kunde_ansprechpartner or '—'}<br/>"
        f"<b>E-Mail:</b> {q.kunde_email or '—'}<br/>"
        f"<b>Referenz Kunde:</b> {q.belegnummer or '—'}"
    )


def _items_table(quotation: Quotation, styles, colors):
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    header = ["Pos", "Artikel-Nr.", "Bezeichnung",
              "Menge", "Einzelpreis", "Gesamt", "Hinweis"]
    data = [header]

    normal = styles["Normal"]
    for it in quotation.items:
        data.append([
            str(it.pos_nr),
            it.artikel_nr,
            Paragraph(it.bezeichnung[:120], normal),
            f"{it.menge:.0f} {it.einheit}",
            f"{it.einzelpreis:.2f} €",
            f"{it.gesamtpreis:.2f} €",
            Paragraph(it.bemerkung, normal) if it.bemerkung else "",
        ])
    data.append([
        "", "", "", "", "Gesamt:",
        f"{quotation.gesamtsumme:.2f} €", "",
    ])

    tbl = Table(data, colWidths=[
        1 * cm, 3 * cm, 5.5 * cm, 2 * cm, 2.2 * cm, 2.2 * cm, 2.5 * cm,
    ])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0E0E0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    return tbl


def _footer(canvas, doc) -> None:
    """Page number + DRAFT watermark at bottom of every page."""
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillGray(0.4)
    canvas.drawString(2 * cm, 1 * cm, "DRAFT - not for external use")
    canvas.drawRightString(
        doc.pagesize[0] - 2 * cm, 1 * cm,
        f"Seite {doc.page}",
    )
    canvas.restoreState()
