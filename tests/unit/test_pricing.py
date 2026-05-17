"""Pricing: discounts, certificates, price resolution."""
from pathlib import Path

from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.pricing import build_quotation

ROW = {
    "artikel_nr": "001GLP108015",
    "bezeichnung": "Gleitstück PTFE 108x15",
    "basispreis_eur": "100.00",
    "zkalk_offset_eur": "5.00",
}

CERT_ROW = {
    "artikel_nr": "001APZ00031B",
    "bezeichnung": "Abnahmeprüfzeugnis 3.1",
    "basispreis_eur": "45.00",
    "zkalk_offset_eur": "0.00",
}


def test_quotation_no_discount_below_100(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[make_position(menge=10)])
    matches = [exact_match_factory(ROW)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert q.items[0].rabatt_prozent == 0.0
    # einzelpreis = 100 * 1.0 + 5 = 105
    assert q.items[0].einzelpreis == 105.0
    assert q.items[0].gesamtpreis == 1050.0


def test_quotation_discount_at_500(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[make_position(menge=500)])
    matches = [exact_match_factory(ROW)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert q.items[0].rabatt_prozent == 10.0
    # einzelpreis = 100 * 0.9 + 5 = 95
    assert q.items[0].einzelpreis == 95.0
    assert q.items[0].gesamtpreis == 47500.0


def test_certificate_uses_quantity_without_volume_discount(make_position, exact_match_factory):
    # Certificates must NOT get volume discount, but quantity still applies.
    anfrage = Anfrage(positionen=[make_position(
        artikelnummer="001APZ00031B",
        bezeichnung="Abnahmeprüfzeugnis 3.1",
        menge=1000,  # would normally trigger 15% discount
        ist_zertifikat=True,
    )])
    matches = [exact_match_factory(CERT_ROW)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert q.items[0].rabatt_prozent == 0.0
    assert q.items[0].einzelpreis == 45.0
    assert q.items[0].gesamtpreis == 45000.0


def test_no_match_adds_warning(make_position):
    anfrage = Anfrage(positionen=[make_position(artikelnummer="UNKNOWN")])
    matches = [MatchResult(pos_nr=1, status="no_match", score=0.0)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert len(q.warnungen) == 1
    assert "no match" in q.warnungen[0].lower()
    assert q.items[0].einzelpreis == 0.0


def test_fuzzy_match_adds_warning(make_position):
    anfrage = Anfrage(positionen=[make_position()])
    matches = [MatchResult(
        pos_nr=1, status="fuzzy", score=0.88,
        matched_artikelnr=ROW["artikel_nr"],
        matched_bezeichnung=ROW["bezeichnung"],
        matched_row=ROW,
    )]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert any("fuzzy" in w.lower() for w in q.warnungen)


def test_custom_article_uses_entered_unit_price_without_volume_discount(make_position):
    anfrage = Anfrage(positionen=[make_position(menge=500)])
    matches = [
        MatchResult(
            pos_nr=1,
            status="exact",
            score=1.0,
            matched_artikelnr="CUST-001",
            matched_bezeichnung="Custom Dichtung",
            matched_row={
                "artikel_nr": "CUST-001",
                "bezeichnung": "Custom Dichtung",
                "basispreis_eur": 12.35,
                "zkalk_offset_eur": 0.0,
                "custom": True,
            },
        )
    ]

    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))

    assert q.items[0].rabatt_prozent == 0.0
    assert q.items[0].einzelpreis == 12.35
    assert q.items[0].gesamtpreis == 6175.0


def test_total_sums_all_items(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[
        make_position(pos_nr=10, menge=10),
        make_position(pos_nr=20, menge=20),
    ])
    matches = [exact_match_factory(ROW), exact_match_factory(ROW)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    assert q.gesamtsumme == sum(it.gesamtpreis for it in q.items)
