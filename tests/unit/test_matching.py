"""Matcher: exact / fuzzy / composite / no_match."""
from quoting.matching import match_positions
from quoting.matching.matcher import _normalize, _normalize_dimension


def test_normalize_preserves_digits_and_hyphens():
    assert _normalize(" 001-GLP 108 ") == "001-GLP108"


def test_normalize_empty():
    assert _normalize("") == ""
    assert _normalize(None) == ""  # type: ignore[arg-type]


def test_normalize_dimension_removes_units_and_normalizes_separator():
    assert _normalize_dimension("108 × 15 mm") == "108X15"
    assert _normalize_dimension("12,5 x 8") == "12.5X8"


def test_exact_match_ignores_whitespace_and_case(make_position, sample_stammdaten):
    positions = [make_position(artikelnummer=" 001glp108015 ")]
    res = match_positions(positions, sample_stammdaten)
    assert res[0].status == "exact"
    assert res[0].score == 1.0
    assert res[0].matched_artikelnr == "001GLP108015"


def test_fuzzy_match_single_typo(make_position, sample_stammdaten):
    positions = [make_position(artikelnummer="001GLP108O15")]  # O vs 0
    res = match_positions(positions, sample_stammdaten, fuzzy_threshold=85)
    assert res[0].status == "fuzzy"
    assert 0.85 <= res[0].score < 1.0


def test_no_match_when_nothing_close(make_position, sample_stammdaten):
    positions = [make_position(
        artikelnummer="ZZZZ999999",
        bezeichnung="Völlig anderes Teil",
    )]
    res = match_positions(positions, sample_stammdaten, fuzzy_threshold=85, semantic_threshold=70)
    assert res[0].status == "no_match"


def test_semantic_match_on_description(make_position, sample_stammdaten):
    positions = [make_position(
        artikelnummer="",
        bezeichnung="Gleitstück aus PTFE 108x15",
        abmessungen="108 x 15 mm",
    )]
    res = match_positions(positions, sample_stammdaten, semantic_threshold=70)
    assert res[0].status == "semantic"
    assert res[0].matched_artikelnr is not None


def test_semantic_match_uses_dimensions_to_disambiguate_variants(make_position):
    stammdaten = [
        {
            "artikel_nr": "A-10815",
            "bezeichnung": "Gleitstück PTFE",
            "werkstoff": "PTFE",
            "abmessungen": "108x15",
        },
        {
            "artikel_nr": "A-08203",
            "bezeichnung": "Gleitstück PTFE",
            "werkstoff": "PTFE",
            "abmessungen": "82x3",
        },
    ]
    positions = [make_position(
        artikelnummer="",
        bezeichnung="Gleitstück PTFE",
        werkstoff="PTFE",
        abmessungen="82 x 3 mm",
    )]

    res = match_positions(positions, stammdaten, semantic_threshold=70)

    assert res[0].status == "semantic"
    assert res[0].matched_artikelnr == "A-08203"


def test_semantic_match_uses_material_context_for_short_description(make_position):
    stammdaten = [
        {
            "artikel_nr": "02599900KS0001",
            "bezeichnung": "Ventilsitz SD1 RSS 40 PTFE mod.",
            "werkstoff": "PTFE",
            "abmessungen": "",
        },
        {
            "artikel_nr": "04255940KS0001",
            "bezeichnung": "Ventilsitz aus PTFE 25% Glas",
            "werkstoff": "PTFE",
            "abmessungen": "",
        },
    ]
    positions = [make_position(
        artikelnummer="",
        bezeichnung="Ventilsitz",
        werkstoff="PTFE 25% Glas",
    )]

    res = match_positions(positions, stammdaten, semantic_threshold=70)

    assert res[0].status == "semantic"
    assert res[0].matched_artikelnr == "04255940KS0001"


def test_preserves_position_order(make_position, sample_stammdaten):
    positions = [
        make_position(artikelnummer="001GLP108015"),
        make_position(artikelnummer="ZZZZ"),
        make_position(artikelnummer="002GLS082003"),
    ]
    res = match_positions(positions, sample_stammdaten)
    assert res[0].status == "exact"
    assert res[1].status == "no_match"
    assert res[2].status == "exact"
