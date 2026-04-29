"""Flowable construction for the offer PDF."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ....core import Anfrage
from ....pricing import Quotation
from .config import OfferPdfConfig
from .formatting import format_eur_de, format_qty, html_escape
from .styles import build_styles


def build_story(
    anfrage: Anfrage,
    quotation: Quotation,
    doc_width: float,
    config: OfferPdfConfig,
) -> list[Any]:
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer

    styles = build_styles()
    today = datetime.now()
    valid_until = today + timedelta(days=config.validity_days)

    story: list[Any] = []
    story.append(address_block(quotation, doc_width, config, styles))
    story.append(Spacer(1, 0.25 * cm))
    story.append(offer_meta_table(quotation, today, valid_until, doc_width, config, styles))
    story.append(Spacer(1, 0.45 * cm))
    story.append(Paragraph(greeting(quotation), styles["body"]))

    for line in config.intro_lines:
        story.append(Paragraph(html_escape(line), styles["body"]))

    # Draft warning banner — suppressed for final PDFs.
    if not config.is_final:
        story.append(Spacer(1, 0.15 * cm))
        story.append(ai_notice(doc_width, config, styles))

    story.append(Spacer(1, 0.45 * cm))
    story.append(items_table(anfrage, quotation, doc_width, config, styles))
    story.append(Spacer(1, 0.35 * cm))
    story.append(total_table(quotation, doc_width))
    story.append(Spacer(1, 0.45 * cm))

    # Internal notes only on draft PDFs — these are review hints,
    # not customer-facing content.
    if not config.is_final:
        story.extend(internal_notes(anfrage, quotation, styles))

    story.extend(closing_flowables(config, styles))
    return story


def address_block(
    quotation: Quotation,
    width: float,
    config: OfferPdfConfig,
    styles: dict[str, Any],
):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    recipient_parts = [f"<b>{html_escape(quotation.kunde_firma or 'Kunde')}</b>"]
    if quotation.kunde_ansprechpartner:
        recipient_parts.append(html_escape(quotation.kunde_ansprechpartner))
    if quotation.kunde_email:
        recipient_parts.append(html_escape(quotation.kunde_email))

    sender = Paragraph(
        f"<b>{html_escape(config.company_name)}</b><br/>{config.company_address_html}",
        styles["sender"],
    )
    recipient = Paragraph("<br/>".join(recipient_parts), styles["address"])

    table = Table(
        [[sender, ""], [recipient, ""]],
        colWidths=[width * 0.58, width * 0.42],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
    ]))
    return table


def offer_meta_table(
    quotation: Quotation,
    today: datetime,
    valid_until: datetime,
    width: float,
    config: OfferPdfConfig,
    styles: dict[str, Any],
):
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = [
        ("Anfragenummer / Datum:", f"{quotation.belegnummer or '-'} / {today.strftime('%d.%m.%Y')}"),
        ("Gültig bis:", valid_until.strftime("%d.%m.%Y")),
        ("Kundenansprechpartner:", quotation.kunde_ansprechpartner or "-"),
        ("E-Mail:", quotation.kunde_email or "-"),
        ("Lieferbedingung:", quotation.incoterms or config.delivery_term),
        ("Zahlungsbedingung:", quotation.zahlungsbedingungen or config.payment_term),
    ]

    data = [
        [
            Paragraph(f"<b>{html_escape(label)}</b>", styles["small"]),
            Paragraph(html_escape(value), styles["small"]),
        ]
        for label, value in rows
    ]

    table = Table(
        data,
        colWidths=[3.5 * cm, width - 3.5 * cm],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def ai_notice(width: float, config: OfferPdfConfig, styles: dict[str, Any]):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    table = Table(
        [[Paragraph(html_escape(config.ai_notice), styles["notice"])]],
        colWidths=[width],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E30613")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5F5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def items_table(
    anfrage: Anfrage,
    quotation: Quotation,
    width: float,
    config: OfferPdfConfig,
    styles: dict[str, Any],
):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    col_widths = [
        0.8 * cm,
        3.25 * cm,
        4.9 * cm,
        2.1 * cm,
        1.35 * cm,
        2.5 * cm,
        1.0 * cm,
    ]
    delta = width - sum(col_widths)
    if delta > 0:
        col_widths[2] += delta

    data: list[list[Any]] = [[
        "Pos",
        "Artikelnr.",
        "Bezeichnung",
        "Menge",
        "ME",
        "Preis EUR",
        "PE",
    ]]

    certificate_positions = {
        pos.pos_nr for pos in anfrage.positionen if pos.ist_zertifikat
    }
    positions_by_nr = {pos.pos_nr: pos for pos in anfrage.positionen}

    for item in quotation.items:
        source_pos = positions_by_nr.get(item.pos_nr)
        price_unit = 1 if item.pos_nr in certificate_positions else 100
        display_price = item.einzelpreis * price_unit

        data.append([
            str(item.pos_nr),
            html_escape(item.artikel_nr),
            Paragraph(html_escape(item.bezeichnung), styles["table"]),
            format_qty(item.menge),
            html_escape(item.einheit),
            format_eur_de(display_price),
            str(price_unit),
        ])

        if item.bemerkung:
            data.append([
                "",
                Paragraph("Hinweis:", styles["table_small"]),
                Paragraph(html_escape(item.bemerkung), styles["table_small"]),
                "",
                "",
                "",
                "",
            ])

        data.append([
            "",
            Paragraph("Lieferzeit:", styles["table_small"]),
            Paragraph(
                html_escape(_position_text(source_pos, "lieferzeit", config.delivery_time)),
                styles["table_small"],
            ),
            "",
            "",
            "",
            "",
        ])
        data.append([
            "",
            Paragraph("Lieferwerk:", styles["table_small"]),
            Paragraph(
                html_escape(_position_text(source_pos, "lieferwerk", config.delivery_plant)),
                styles["table_small"],
            ),
            "",
            "",
            "",
            "",
        ])
        data.append(["", "", "", "", "", "", ""])

    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1.1, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.2),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("ALIGN", (6, 1), (6, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _position_text(pos, field_name: str, fallback: str) -> str:
    value = getattr(pos, field_name, None) if pos is not None else None
    text = str(value or "").strip()
    return text or fallback


def total_table(quotation: Quotation, width: float):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle

    label_w = 4.0 * cm
    value_w = 3.0 * cm
    filler_w = max(0, width - label_w - value_w)

    table = Table(
        [["", "Gesamtsumme netto:", f"{format_eur_de(quotation.gesamtsumme)} EUR"]],
        colWidths=[filler_w, label_w, value_w],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("LINEABOVE", (1, 0), (-1, 0), 0.8, colors.black),
        ("FONTNAME", (1, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (1, 0), (-1, -1), 8.5),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def internal_notes(
    anfrage: Anfrage,
    quotation: Quotation,
    styles: dict[str, Any],
) -> list[Any]:
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer

    notes = list(quotation.warnungen)
    notes.extend(f"Extraktion: {u}" for u in anfrage.unsicherheiten)

    if not notes:
        return []

    flowables: list[Any] = [
        Paragraph("Interne Hinweise zur Freigabe", styles["section_heading"]),
    ]
    for note in notes:
        flowables.append(Paragraph(f"- {html_escape(note)}", styles["small"]))
    flowables.append(Spacer(1, 0.35 * cm))
    return flowables


def closing_flowables(
    config: OfferPdfConfig,
    styles: dict[str, Any],
) -> list[Any]:
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer

    flowables: list[Any] = []
    for line in config.effective_closing():
        flowables.append(Paragraph(html_escape(line), styles["body"]))
        flowables.append(Spacer(1, 0.1 * cm))
    return flowables


def greeting(quotation: Quotation) -> str:
    contact = (quotation.kunde_ansprechpartner or "").strip()
    if contact:
        return f"Sehr geehrte Damen und Herren, z. Hd. {html_escape(contact)},"
    return "Sehr geehrte Damen und Herren,"
