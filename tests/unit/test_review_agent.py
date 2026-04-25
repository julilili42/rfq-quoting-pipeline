"""Tests for review chat-agent helpers."""
from pathlib import Path

from quoting.core import Anfrage
from quoting.pricing import build_quotation
from quoting.ui.review_agent import (
    apply_manual_overrides,
    build_general_agent_reply,
    detect_agent_language,
    parse_edit_instruction,
    parse_discount_instruction,
    upsert_override,
)


ROW = {
    "artikel_nr": "001GLP108015",
    "bezeichnung": "Gleitstueck PTFE 108x15",
    "basispreis_eur": "100.00",
    "zkalk_offset_eur": "5.00",
}


def test_parse_discount_for_article():
    override, feedback = parse_discount_instruction(
        "Gib 7% Rabatt auf Artikel 001GLP108015",
        ["001GLP108015"],
    )
    assert override is not None
    assert override["target"] == "artikel"
    assert override["artikel_nr"] == "001GLP108015"
    assert override["discount_pct"] == 7.0
    assert "7.0%" in feedback


def test_parse_discount_for_position():
    override, _ = parse_edit_instruction("discount 5% for pos 2", [])
    assert override is not None
    assert override["target"] == "pos"
    assert override["pos_nr"] == 2
    assert override["discount_pct"] == 5.0


def test_parse_fixed_price_for_position_german_phrase():
    override, feedback = parse_edit_instruction("Kannst du bitte fuer die pos 3 10 euro machen", [])
    assert override is not None
    assert override["target"] == "pos"
    assert override["pos_nr"] == 3
    assert override["mode"] == "unit_price_eur"
    assert override["unit_price_eur"] == 10.0
    assert "10.00" in feedback


def test_parse_fixed_price_compact_and_symbol_format():
    override, _ = parse_edit_instruction("mach pos3 auf 10€", [])
    assert override is not None
    assert override["target"] == "pos"
    assert override["pos_nr"] == 3
    assert override["mode"] == "unit_price_eur"
    assert override["unit_price_eur"] == 10.0


def test_parse_total_price_for_position():
    override, feedback = parse_edit_instruction("set total for pos 3 to 70 eur", [], lang="en")
    assert override is not None
    assert override["mode"] == "total_price_eur"
    assert override["total_price_eur"] == 70.0
    assert "total price" in feedback.lower()


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


def test_parse_non_discount_message_returns_none():
    override, feedback = parse_discount_instruction("What is the total amount?", ["001GLP108015"])
    assert override is None
    assert feedback == ""


def test_detect_agent_language_maps_cyrillic_to_english():
    lang = detect_agent_language("Добрый день, просим рассчитать цену и срок поставки")
    assert lang == "en"


def test_detect_agent_language_detects_english():
    lang = detect_agent_language("Please provide quotation and delivery schedule")
    assert lang == "en"


def test_parse_feedback_localized_german():
    override, feedback = parse_discount_instruction(
        "Bitte gib 6% Rabatt auf Artikel 001GLP108015",
        ["001GLP108015"],
        lang="de",
    )
    assert override is not None
    assert "Rabatt" in feedback


def test_general_reply_localized_by_language(make_position, exact_match_factory):
    anfrage = Anfrage(positionen=[make_position(pos_nr=1, artikelnummer="001GLP108015", menge=1)])
    matches = [exact_match_factory(ROW, pos_nr=1)]
    q = build_quotation(anfrage, matches, Path("/nonexistent.csv"))

    reply = build_general_agent_reply("total?", q, lang="en")
    assert "Current total amount" in reply
