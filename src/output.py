"""
Output-Modul
============
Erstellt Draft-Angebots-PDF und speichert Zwischenergebnisse als JSON.
Nutzt reportlab für PDF (keine Browser-/System-Dependencies).
"""
from pathlib import Path
import json
from typing import Any

from extractor import Anfrage


def speichere_json(data: Any, pfad: Path) -> None:
    """Speichert beliebiges JSON-serialisierbares Objekt."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def erstelle_draft_pdf(
    anfrage: Anfrage,
    matches: list[dict],
    quotation: dict,
    pfad: Path,
) -> None:
    """
    Erzeugt ein Draft-Angebots-PDF mit:
    - Kundendaten + Referenz
    - Positionstabelle (mit Preis + Bemerkung)
    - Warnhinweisen bei unklaren Matches
    - Deutlichem DRAFT-Wasserzeichen
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        )
    except ImportError:
        print("   ⚠️  reportlab nicht installiert, schreibe JSON statt PDF")
        speichere_json(quotation, pfad.with_suffix(".json"))
        return

    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pfad), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    draft_style = ParagraphStyle(
        "Draft", parent=styles["Heading1"],
        textColor=colors.red, alignment=1, fontSize=20,
    )
    h2 = styles["Heading2"]
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("DRAFT - ZUR INTERNEN PRÜFUNG", draft_style))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Angebot (Entwurf)", styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))

    # Kundendaten
    kunde_text = (
        f"<b>Kunde:</b> {quotation.get('kunde_firma') or '—'}<br/>"
        f"<b>Ansprechpartner:</b> {quotation.get('kunde_ansprechpartner') or '—'}<br/>"
        f"<b>E-Mail:</b> {quotation.get('kunde_email') or '—'}<br/>"
        f"<b>Referenz Kunde:</b> {quotation.get('belegnummer') or '—'}"
    )
    story.append(Paragraph(kunde_text, normal))
    story.append(Spacer(1, 0.5 * cm))

    # Positionstabelle
    story.append(Paragraph("Positionen", h2))
    header = ["Pos", "Artikel-Nr.", "Bezeichnung",
              "Menge", "Einzelpreis", "Gesamt", "Hinweis"]
    table_data = [header]
    for item in quotation["items"]:
        table_data.append([
            str(item["pos_nr"]),
            item["artikel_nr"],
            Paragraph(item["bezeichnung"][:120], normal),
            f"{item['menge']:.0f} {item['einheit']}",
            f"{item['einzelpreis']:.2f} €",
            f"{item['gesamtpreis']:.2f} €",
            Paragraph(item["bemerkung"], normal) if item["bemerkung"] else "",
        ])
    # Summenzeile
    table_data.append([
        "", "", "", "", "Gesamt:",
        f"{quotation['gesamtsumme']:.2f} €", ""
    ])

    tbl = Table(table_data, colWidths=[
        1 * cm, 3 * cm, 5.5 * cm, 2 * cm, 2.2 * cm, 2.2 * cm, 2.5 * cm
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
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))

    # Konditionen
    story.append(Paragraph("Konditionen", h2))
    kond_text = (
        f"<b>Incoterms:</b> {quotation.get('incoterms') or '—'}<br/>"
        f"<b>Zahlungsbedingungen:</b> {quotation.get('zahlungsbedingungen') or '—'}"
    )
    story.append(Paragraph(kond_text, normal))
    story.append(Spacer(1, 0.5 * cm))

    # Warnungen
    if quotation.get("warnungen"):
        story.append(Paragraph("⚠️ Hinweise zur Freigabe", h2))
        for w in quotation["warnungen"]:
            story.append(Paragraph(f"• {w}", normal))
        story.append(Spacer(1, 0.3 * cm))

    if anfrage.unsicherheiten:
        story.append(Paragraph("🔍 Unsicherheiten aus der Extraktion", h2))
        for u in anfrage.unsicherheiten:
            story.append(Paragraph(f"• {u}", normal))

    # Audit-Seite mit Source-Quotes
    story.append(PageBreak())
    story.append(Paragraph("Audit-Protokoll (Extraktion)", h2))
    for pos in anfrage.positionen:
        story.append(Paragraph(
            f"<b>Pos {pos.pos_nr}</b> (Confidence: {pos.confidence})<br/>"
            f'<i>Quelle:</i> "{pos.source_quote}"',
            normal,
        ))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
