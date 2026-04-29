"""Schema validators."""
from quoting.core import Anfrage, Position


def _kwargs(**over):
    base = dict(
        pos_nr=1, artikelnummer="X", bezeichnung="b",
        menge=1, einheit="Stk", confidence="high", source_quote="q",
    )
    base.update(over)
    return base


def test_artikelnummer_whitespace_collapsed():
    p = Position(**_kwargs(artikelnummer="  001 GLP  108015  "))
    assert p.artikelnummer == "001 GLP 108015"


def test_menge_accepts_german_decimal():
    p = Position(**_kwargs(menge="1,5"))
    assert p.menge == 1.5


def test_menge_accepts_int_string():
    p = Position(**_kwargs(menge="500"))
    assert p.menge == 500.0


def test_defaults_for_optional_fields():
    p = Position(**_kwargs())
    assert p.lieferzeit is None
    assert p.lieferwerk is None
    assert p.werkstoff is None
    assert p.werkstoff_alternativen == []
    assert p.ist_zertifikat is False


def test_anfrage_with_empty_positions():
    a = Anfrage(positionen=[])
    assert a.kundennummer is None
    assert a.positionen == []
    assert a.unsicherheiten == []
