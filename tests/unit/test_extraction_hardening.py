from __future__ import annotations

from quoting.core import Anfrage, Position
from quoting.core.schema import Evidence
from quoting.extraction.candidates import build_candidate_hints
from quoting.extraction.source_guard import harden_extraction_with_sources


def test_candidate_hints_include_exact_header_and_position_values():
    hints = build_candidate_hints(
        "Bitte anbieten. Belegnummer 2026-50422",
        [
            "=== PDF TEXT: Anfrage.pdf ===\n"
            "Kunden-Nr. 17390 Email f.hochstein@goehmann.com "
            "Datum 06.02.2026 Pos 10 001GLP108015 100 Stk"
        ],
    )

    assert "2026-50422" in hints
    assert "17390" in hints
    assert "f.hochstein@goehmann.com" in hints
    assert "06.02.2026" in hints
    assert "001GLP108015" in hints


def test_source_guard_clears_unsubstantiated_customer_header_values():
    anfrage = Anfrage(
        kunde_firma="Göhmann & Co. GmbH",
        kunde_ansprechpartner="Max Hochstein",
        kunde_email="max.hochstein@goehmann.com",
        belegnummer="2026-50422",
        datum="06.02.2026",
        kundennummer="17390",
        positionen=[],
        header_evidence={
            "kunde_ansprechpartner": Evidence(source_quote="Max Hochstein"),
            "kunde_email": Evidence(source_quote="max.hochstein@goehmann.com"),
        },
    )
    sections = [
        "=== PDF TEXT: Anfrage.pdf ===\n"
        "Göhmann & Co. GmbH Bearbeiter Felix Hochstein "
        "Email f.hochstein@goehmann.com Kunden-Nr. 17390 "
        "Belegnummer 2026-50422 Datum 06.02.2026"
    ]

    changes = harden_extraction_with_sources(anfrage, "", sections)

    assert "kunde_ansprechpartner" in changes
    assert "kunde_email" in changes
    assert anfrage.kunde_ansprechpartner is None
    assert anfrage.kunde_email is None
    assert anfrage.kunde_firma == "Göhmann & Co. GmbH"
    assert anfrage.belegnummer == "2026-50422"
    assert anfrage.datum == "06.02.2026"
    assert anfrage.kundennummer == "17390"
    assert "kunde_ansprechpartner" not in anfrage.header_evidence
    assert "kunde_email" not in anfrage.header_evidence
    assert anfrage.unsicherheiten


def test_source_guard_downgrades_position_when_article_is_not_in_text():
    pos = Position(
        pos_nr=10,
        artikelnummer="001GLP999999",
        bezeichnung="Gleitstück",
        menge=5,
        einheit="Stk",
        confidence="high",
        source_quote="Pos 10 001GLP999999 5 Stk",
    )
    anfrage = Anfrage(positionen=[pos])

    changes = harden_extraction_with_sources(
        anfrage,
        "",
        ["=== PDF TEXT: Anfrage.pdf ===\nPos 10 001GLP108015 5 Stk"],
    )

    assert "position:10:confidence" in changes
    assert anfrage.positionen[0].confidence == "low"
    assert anfrage.unsicherheiten


def test_source_guard_does_not_clear_values_for_vision_only_sources():
    anfrage = Anfrage(
        kunde_ansprechpartner="Max Hochstein",
        kunde_email="max.hochstein@goehmann.com",
        positionen=[],
    )

    changes = harden_extraction_with_sources(
        anfrage,
        "",
        [
            "=== PDF: scan.pdf ===",
            "=== IMAGE ORDER (VISION INPUTS) ===",
            "Image 1: PDF scan.pdf, page 1 of 1",
        ],
    )

    assert changes == []
    assert anfrage.kunde_ansprechpartner == "Max Hochstein"
    assert anfrage.kunde_email == "max.hochstein@goehmann.com"


def test_source_guard_does_not_use_generic_mail_body_to_clear_scan_values():
    anfrage = Anfrage(
        kunde_ansprechpartner="Max Hochstein",
        kunde_email="max.hochstein@goehmann.com",
        positionen=[],
    )

    changes = harden_extraction_with_sources(
        anfrage,
        "Sehr geehrte Damen und Herren, bitte beachten Sie die angehängte Anfrage.",
        [
            "=== PDF: scan.pdf ===",
            "=== IMAGE ORDER (VISION INPUTS) ===",
            "Image 1: PDF scan.pdf, page 1 of 1",
        ],
    )

    assert changes == []
    assert anfrage.kunde_ansprechpartner == "Max Hochstein"
    assert anfrage.kunde_email == "max.hochstein@goehmann.com"
