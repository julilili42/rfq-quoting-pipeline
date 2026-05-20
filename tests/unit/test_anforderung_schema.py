"""Schema validation for the Anforderung type and its embedding in Anfrage."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from quoting.core import Anforderung, Anfrage


def test_anforderung_minimal_fields():
    item = Anforderung(text="Zeichnung beilegen", kategorie="zeichnung")
    assert item.pos_nr is None
    assert item.source_quote == ""


def test_anforderung_rejects_unknown_kategorie():
    with pytest.raises(ValidationError):
        Anforderung(text="x", kategorie="banane")  # type: ignore[arg-type]


def test_anforderung_pos_nr_optional_int():
    item = Anforderung(text="Zertifikat 3.1", kategorie="zertifikat", pos_nr=30)
    assert item.pos_nr == 30


def test_anfrage_anforderungen_defaults_empty():
    anfrage = Anfrage(positionen=[])
    assert anfrage.anforderungen == []


def test_anfrage_anforderungen_round_trip():
    anfrage = Anfrage(
        positionen=[],
        anforderungen=[
            Anforderung(
                text="Lieferung in Holzkiste",
                kategorie="verpackung",
                source_quote="Lieferung bitte in Holzkiste.",
            )
        ],
    )
    dumped = anfrage.model_dump(mode="json")
    restored = Anfrage.model_validate(dumped)
    assert len(restored.anforderungen) == 1
    assert restored.anforderungen[0].kategorie == "verpackung"
    assert restored.anforderungen[0].pos_nr is None
