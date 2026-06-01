from __future__ import annotations

from reportlab.platypus import Paragraph

from quoting.core import Anfrage, Position
from quoting.output.pdf.offer.config import OfferPdfConfig
from quoting.output.pdf.offer.flowables import items_table
from quoting.output.pdf.offer.styles import build_styles
from quoting.pricing import Quotation, QuotationItem


def _plain(value: object) -> str:
    if isinstance(value, Paragraph):
        return value.getPlainText()
    return str(value)


def test_position_weight_renders_as_pdf_position_detail_field() -> None:
    anfrage = Anfrage(
        kunde_firma="Muster GmbH",
        positionen=[
            Position(
                pos_nr=10,
                artikelnummer="ART-10",
                bezeichnung="Gleitstück",
                menge=5,
                einheit="Stk",
                lieferzeit="6 Wochen",
                lieferwerk="Werk A",
                gewicht_netto_kg=12.5,
                gewicht_brutto_kg=14,
                confidence="high",
                source_quote="Pos 10 ART-10 5 Stk",
            )
        ],
    )
    quotation = Quotation(
        kunde_firma="Muster GmbH",
        kunde_ansprechpartner="Max Mustermann",
        kunde_email="max@example.com",
        kundennummer="K-100",
        belegnummer="RFQ-1",
        incoterms=None,
        zahlungsbedingungen=None,
        items=[
            QuotationItem(
                pos_nr=10,
                artikel_nr="ART-10",
                bezeichnung="Gleitstück",
                menge=5,
                einheit="Stk",
                einzelpreis=2.5,
                rabatt_prozent=0,
                gesamtpreis=12.5,
                bemerkung="",
            )
        ],
        gesamtsumme=12.5,
        waehrung="EUR",
        warnungen=[],
    )

    table = items_table(
        anfrage,
        quotation,
        width=500,
        config=OfferPdfConfig(is_final=True),
        styles=build_styles(),
    )

    # items_table returns a single Table; skip the header row (index 0).
    # Detail fields are on separate rows: label in col 1, value in col 2.
    rows = [[_plain(cell) for cell in row] for row in table._cellvalues]
    assert ["", "Gewicht:", "Netto 12,5 kg / Brutto 14 kg", "", "", "", ""] in rows
