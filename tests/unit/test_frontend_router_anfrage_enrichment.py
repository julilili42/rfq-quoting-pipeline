from quoting.api import _common, frontend_router
from quoting.api.frontend_router import (
    _enrich_exact_article_edits,
    _filter_redundant_custom_price_overrides,
    _remove_position_price_overrides,
)
from quoting.api.services.review_service import ReviewDataService
from quoting.core import Anfrage
from quoting.data import InMemoryStammdatenRepository, StammdatenRecord
from quoting.matching import MatchResult
from quoting.reviews import Payloads


class _PipelineStub:
    def __init__(self):
        self.stammdaten_repo = InMemoryStammdatenRepository(
            [
                StammdatenRecord(
                    artikel_nr="001GLP108015",
                    bezeichnung="Gleitstück aus Stammdaten",
                    werkstoff="PTFE/Graphit",
                    abmessungen="108 x 15 mm",
                    einheit="Stk",
                )
            ]
        )


def test_exact_article_edit_fills_stammdaten_fields(make_position):
    previous = Anfrage(
        positionen=[make_position(pos_nr=1, artikelnummer="", bezeichnung="")]
    )
    anfrage = Anfrage(
        positionen=[
            make_position(
                pos_nr=1,
                artikelnummer=" 001glp108015 ",
                bezeichnung="",
                werkstoff=None,
                abmessungen=None,
            )
        ]
    )

    enriched = _enrich_exact_article_edits(anfrage, previous, _PipelineStub())  # type: ignore[arg-type]
    pos = enriched.positionen[0]

    assert pos.artikelnummer == "001GLP108015"
    assert pos.bezeichnung == "Gleitstück aus Stammdaten"
    assert pos.werkstoff == "PTFE/Graphit"
    assert pos.abmessungen == "108 x 15 mm"


def test_same_article_does_not_overwrite_manual_description(make_position):
    previous = Anfrage(
        positionen=[
            make_position(
                pos_nr=1,
                artikelnummer="001GLP108015",
                bezeichnung="Alte Bezeichnung",
            )
        ]
    )
    anfrage = Anfrage(
        positionen=[
            make_position(
                pos_nr=1,
                artikelnummer="001GLP108015",
                bezeichnung="Manuell geändert",
            )
        ]
    )

    enriched = _enrich_exact_article_edits(anfrage, previous, _PipelineStub())  # type: ignore[arg-type]

    assert enriched.positionen[0].bezeichnung == "Manuell geändert"


def test_custom_article_match_persists_review_local_article(
    sqlite_repo,
    monkeypatch,
    make_position,
):
    review_id = "review-1"
    sqlite_repo.create_review(review_id)
    anfrage = Anfrage(
        positionen=[
            make_position(
                pos_nr=1,
                artikelnummer="",
                bezeichnung="Alte Beschreibung",
                menge=2,
                werkstoff=None,
                abmessungen=None,
            )
        ]
    )
    sqlite_repo.save_anfrage_reviewed(review_id, anfrage.model_dump(mode="json"))
    sqlite_repo.save_matches_reviewed(
        review_id,
        [
            {
                "pos_nr": 1,
                "status": "no_match",
                "score": 0.0,
                "matched_artikelnr": None,
                "matched_bezeichnung": None,
                "matched_row": None,
            }
        ],
    )
    sqlite_repo.save_overrides(
        review_id,
        [
            {
                "target": "pos",
                "pos_nr": 1,
                "mode": "unit_price_eur",
                "unit_price_eur": 99,
            },
            {
                "target": "pos",
                "pos_nr": 1,
                "mode": "discount_pct",
                "discount_pct": 5,
            },
            {
                "target": "pos",
                "pos_nr": 2,
                "mode": "unit_price_eur",
                "unit_price_eur": 7,
            },
        ],
    )

    monkeypatch.setattr(_common, "_pipeline", _PipelineStub())

    response = frontend_router.create_custom_article_match(
        review_id,
        frontend_router.CustomArticleRequest(
            pos_nr=1,
            artikel_nr=" CUST-001 ",
            bezeichnung=" Custom Dichtung ",
            einheit="Stk",
            unit_price_eur=12.345,
            werkstoff=" PTFE ",
            abmessungen=" 10 x 20 ",
        ),
    )

    assert response == {
        "pos_nr": 1,
        "matched_artikelnr": "CUST-001",
        "matched_bezeichnung": "Custom Dichtung",
        "unit_price_eur": 12.35,
    }

    saved_anfrage = sqlite_repo.load_payload(review_id, Payloads.ANFRAGE_REVIEWED)
    saved_position = saved_anfrage["positionen"][0]
    assert saved_position["artikelnummer"] == "CUST-001"
    assert saved_position["bezeichnung"] == "Custom Dichtung"
    assert saved_position["werkstoff"] == "PTFE"
    assert saved_position["abmessungen"] == "10 x 20"

    saved_match = sqlite_repo.load_payload(review_id, Payloads.MATCHES_REVIEWED)[0]
    assert saved_match["status"] == "exact"
    assert saved_match["matched_artikelnr"] == "CUST-001"
    assert saved_match["matched_row"]["custom"] is True
    assert saved_match["matched_row"]["basispreis_eur"] == 12.35

    overrides = sqlite_repo.load_overrides(review_id)
    assert overrides == [
        {
            "target": "pos",
            "pos_nr": 1,
            "mode": "discount_pct",
            "discount_pct": 5,
        },
        {
            "target": "pos",
            "pos_nr": 2,
            "mode": "unit_price_eur",
            "unit_price_eur": 7,
        }
    ]


def test_custom_article_removes_existing_pos_price_overrides():
    updated = _remove_position_price_overrides(
        [
            {
                "target": "pos",
                "pos_nr": 1,
                "mode": "total_price_eur",
                "total_price_eur": 99,
            },
            {
                "target": "pos",
                "pos_nr": 2,
                "mode": "unit_price_eur",
                "unit_price_eur": 7,
            },
        ],
        pos_nr=1,
    )

    assert updated == [
        {
            "target": "pos",
            "pos_nr": 2,
            "mode": "unit_price_eur",
            "unit_price_eur": 7,
        },
    ]


def test_redundant_custom_price_override_is_hidden_from_review_detail():
    filtered = _filter_redundant_custom_price_overrides(
        [
            {
                "target": "pos",
                "pos_nr": 1,
                "mode": "unit_price_eur",
                "unit_price_eur": 12.35,
            },
            {
                "target": "pos",
                "pos_nr": 1,
                "mode": "discount_pct",
                "discount_pct": 5,
            },
            {
                "target": "pos",
                "pos_nr": 2,
                "mode": "unit_price_eur",
                "unit_price_eur": 7,
            },
        ],
        [
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
                    "custom": True,
                },
            )
        ],
    )

    assert filtered == [
        {
            "target": "pos",
            "pos_nr": 1,
            "mode": "discount_pct",
            "discount_pct": 5,
        },
        {
            "target": "pos",
            "pos_nr": 2,
            "mode": "unit_price_eur",
            "unit_price_eur": 7,
        },
    ]


def test_load_matches_filters_deleted_position_matches(sqlite_repo, make_position):
    review_id = "review-1"
    sqlite_repo.create_review(review_id)
    anfrage = Anfrage(positionen=[make_position(pos_nr=1)])
    sqlite_repo.save_matches_reviewed(
        review_id,
        [
            {
                "pos_nr": 99,
                "status": "exact",
                "score": 1.0,
                "matched_artikelnr": "CUST-OLD",
                "matched_bezeichnung": "Alter Custom-Artikel",
                "matched_row": {"artikel_nr": "CUST-OLD", "custom": True},
            },
            {
                "pos_nr": 1,
                "status": "no_match",
                "score": 0.0,
                "matched_artikelnr": None,
                "matched_bezeichnung": None,
                "matched_row": None,
            },
        ],
    )

    matches = ReviewDataService(sqlite_repo).load_or_recompute_matches(
        review_id,
        anfrage,
        _PipelineStub(),  # type: ignore[arg-type]
    )

    assert [match.pos_nr for match in matches] == [1]
    assert matches[0].matched_artikelnr is None


def test_original_anfrage_loader_ignores_reviewed_edits(sqlite_repo, make_position):
    review_id = "review-1"
    sqlite_repo.create_review(review_id)
    original = Anfrage(positionen=[make_position(pos_nr=1, artikelnummer="ORIGINAL")])
    reviewed = Anfrage(positionen=[make_position(pos_nr=1, artikelnummer="EDITED")])
    sqlite_repo.save_extracted(review_id, original.model_dump(mode="json"))
    sqlite_repo.save_anfrage_reviewed(review_id, reviewed.model_dump(mode="json"))

    loaded = ReviewDataService(sqlite_repo).try_load_original_anfrage(review_id)

    assert loaded is not None
    assert loaded.positionen[0].artikelnummer == "ORIGINAL"
