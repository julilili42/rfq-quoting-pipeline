"""Tests for manual override merging and quotation re-pricing."""
from pathlib import Path

from quoting.core import Anfrage
from quoting.pricing import apply_manual_overrides, build_quotation, upsert_override

ROW = {
    "artikel_nr": "001GLP108015",
    "bezeichnung": "Gleitstueck PTFE 108x15",
    "basispreis_eur": "100.00",
    "zkalk_offset_eur": "5.00",
}


def test_upsert_override_replaces_same_target():
    current = [{"target": "artikel", "artikel_nr": "A1", "discount_pct": 3.0}]
    merged = upsert_override(
        current,
        {"target": "artikel", "artikel_nr": "A1", "discount_pct": 8.0},
    )
    assert len(merged) == 1
    assert merged[0]["discount_pct"] == 8.0


def test_apply_manual_overrides_changes_total(make_position, exact_match_factory):
    anfrage = Anfrage(
        positionen=[
            make_position(pos_nr=1, artikelnummer="001GLP108015", menge=10),
            make_position(pos_nr=2, artikelnummer="001GLP108015", menge=5),
        ]
    )
    matches = [
        exact_match_factory(ROW, pos_nr=1),
        exact_match_factory(ROW, pos_nr=2),
    ]

    base = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    changed, applied = apply_manual_overrides(
        base,
        anfrage,
        [{"target": "pos", "pos_nr": 1, "discount_pct": 10.0}],
    )

    assert applied == 1
    assert changed.gesamtsumme < base.gesamtsumme


def test_apply_article_override_to_all_matching_items(make_position, exact_match_factory):
    anfrage = Anfrage(
        positionen=[
            make_position(pos_nr=1, artikelnummer="001GLP108015", menge=2),
            make_position(pos_nr=2, artikelnummer="001GLP108015", menge=3),
        ]
    )
    matches = [
        exact_match_factory(ROW, pos_nr=1),
        exact_match_factory(ROW, pos_nr=2),
    ]

    base = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    changed, applied = apply_manual_overrides(
        base,
        anfrage,
        [{"target": "artikel", "artikel_nr": "001GLP108015", "discount_pct": 5.0}],
    )

    assert applied == 2
    assert changed.gesamtsumme < base.gesamtsumme
    assert all(("Rabatt" in it.bemerkung) or ("discount" in it.bemerkung.lower()) for it in changed.items)


def test_apply_fixed_unit_price_override(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[make_position(pos_nr=3, artikelnummer="001GLP108015", menge=7)])
    matches = [exact_match_factory(ROW, pos_nr=3)]

    base = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    changed, applied = apply_manual_overrides(
        base,
        anfrage,
        [{"target": "pos", "pos_nr": 3, "mode": "unit_price_eur", "unit_price_eur": 10.0}],
        lang="de",
    )

    assert applied == 1
    assert changed.items[0].einzelpreis == 10.0
    assert changed.items[0].gesamtpreis == 70.0
    assert changed.gesamtsumme == 70.0


def test_apply_fixed_total_price_override(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[make_position(pos_nr=3, artikelnummer="001GLP108015", menge=7)])
    matches = [exact_match_factory(ROW, pos_nr=3)]

    base = build_quotation(anfrage, matches, Path("/nonexistent.csv"))
    changed, applied = apply_manual_overrides(
        base,
        anfrage,
        [{"target": "pos", "pos_nr": 3, "mode": "total_price_eur", "total_price_eur": 70.0}],
        lang="en",
    )

    assert applied == 1
    assert changed.items[0].einzelpreis == 10.0
    assert changed.items[0].gesamtpreis == 70.0
    assert changed.gesamtsumme == 70.0
