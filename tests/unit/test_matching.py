"""Matcher: exact / fuzzy / composite / no_match."""
from quoting.matching import match_positions
from quoting.matching.matcher import _normalize


def test_normalize_preserves_digits_and_hyphens():
    assert _normalize(" 001-GLP 108 ") == "001-GLP108"


def test_normalize_empty():
    assert _normalize("") == ""
    assert _normalize(None) == ""  # type: ignore[arg-type]


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
    )]
    res = match_positions(positions, sample_stammdaten, semantic_threshold=70)
    assert res[0].status == "semantic"
    assert res[0].matched_artikelnr is not None


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
