"""Unit tests for the deterministic fast-path extractor."""
from __future__ import annotations

from pathlib import Path

import pytest

from quoting.data import InMemoryStammdatenRepository, StammdatenRecord
from quoting.extraction.fast_path import (
    FastPathExtractor,
    _extract_quantity,
    _normalize,
    _normalize_with_map,
)
from quoting.ingestion import Mail


# ----------------------------------------------------------- normalization

def test_normalize_strips_separators_and_uppercases():
    assert _normalize("06827480 ET 0001") == "06827480ET0001"
    assert _normalize("06827480-et-0001") == "06827480ET0001"
    assert _normalize("06827480.et.0001") == "06827480ET0001"
    assert _normalize("06827480/et/0001") == "06827480ET0001"


def test_normalize_with_map_recovers_original_positions():
    text = "  06827480 ET 0001 x6"
    norm, idx = _normalize_with_map(text)
    assert norm == "06827480ET0001X6"
    # The "0" in "06827480" is at original index 2.
    assert idx[0] == 2
    # "X" (from "x6") maps back to lowercase 'x'.
    assert text[idx[norm.index("X")]] == "x"


# ----------------------------------------------------------- quantity

@pytest.mark.parametrize("window,expected", [
    (" x6 pcs", 6),
    (", qty 3", 3),
    (" qty: 100 ", 100),
    (" 100 St.", 100),
    (" 6 Stück", 6),
    (" 5 pieces total", 5),
    (" × 50 ea", 50),
    (" Menge: 12", 12),
    ("nothing here", None),
    (" no qty 0 wat", None),  # 0 is below the [1, 99999] band
])
def test_quantity_patterns(window, expected):
    assert _extract_quantity(window) == expected


def test_dimensions_dont_pollute_quantity():
    # "55x63x6" is a dimension, not a quantity. The "x6" inside MUST
    # not be returned as menge=6.
    assert _extract_quantity(" (55x63x6) and that's it") is None


def test_dimensions_with_decimals_stripped():
    # German-style decimal commas in dimensions also stripped.
    assert _extract_quantity(" 1,1x0,5x0,31 mm") is None


def test_dimensions_followed_by_quantity():
    # Dimension first, then a real quantity. Dimension stripped, quantity wins.
    assert _extract_quantity(" 55x63x6 mm, qty 4") == 4


# ----------------------------------------------------------- end-to-end

def _make_repo() -> InMemoryStammdatenRepository:
    return InMemoryStammdatenRepository([
        StammdatenRecord(
            artikel_nr="06827480ET0001",
            bezeichnung="Protection Sleeve Ground 55x63x6",
            werkstoff="PTFE",
            abmessungen="55x63x6",
            einheit="ST",
            basispreis_eur=57.58,
        ),
        StammdatenRecord(
            artikel_nr="07866320ET0001",
            bezeichnung="Test Article",
            einheit="ST",
            basispreis_eur=51.33,
        ),
        StammdatenRecord(
            artikel_nr="00002900KS0009",
            bezeichnung="Nadeldichtung 12x18,2x11,6 HS4080",
            werkstoff=None,
            abmessungen="12x18,2x11,6",
            einheit="ST",
            basispreis_eur=19.10,
        ),
    ])


def test_fast_path_hits_on_simple_mail():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(
        subject="Quote",
        sender="Sliding <sliding@rotec-ltd.com>",
        body="Hi could I please have a price for these. 55x63x6 ElringKlinger AG 06827480ET0001 x6 pcs",
        attachments=[],
    )
    anfrage = fp.try_extract(mail)
    assert anfrage is not None
    assert len(anfrage.positionen) == 1
    pos = anfrage.positionen[0]
    assert pos.artikelnummer == "06827480ET0001"
    assert pos.menge == 6.0
    assert pos.einheit == "ST"  # comes from stammdaten record, not default
    assert pos.bezeichnung == "Protection Sleeve Ground 55x63x6"
    assert pos.confidence == "high"
    assert "06827480ET0001" in pos.source_quote
    assert pos.source_file == "mail"
    assert anfrage.kunde_email == "sliding@rotec-ltd.com"
    assert anfrage.kunde_firma == "Sliding"


def test_fast_path_declines_when_artikelnr_missing_in_stammdaten():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(
        body="Please quote 99999999XX9999, qty 5",
        attachments=[],
    )
    assert fp.try_extract(mail) is None


def test_fast_path_declines_without_quantity():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(body="Need price for 06827480ET0001", attachments=[])
    assert fp.try_extract(mail) is None


def test_fast_path_declines_when_one_of_many_lacks_quantity():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(
        body="Need 06827480ET0001 x6 pcs and also something about 07866320ET0001",
        attachments=[],
    )
    # Second article has no qty in its window → bail out.
    assert fp.try_extract(mail) is None


def test_fast_path_handles_multiple_positions():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(
        body=(
            "Bitte folgendes Angebot:\n"
            "06827480ET0001 x6 pcs\n"
            "07866320ET0001 qty 10"
        ),
        attachments=[],
    )
    anfrage = fp.try_extract(mail)
    assert anfrage is not None
    assert len(anfrage.positionen) == 2
    assert anfrage.positionen[0].artikelnummer == "06827480ET0001"
    assert anfrage.positionen[0].menge == 6.0
    assert anfrage.positionen[1].artikelnummer == "07866320ET0001"
    assert anfrage.positionen[1].menge == 10.0
    # pos_nr must be stable + ordered
    assert anfrage.positionen[0].pos_nr == 10
    assert anfrage.positionen[1].pos_nr == 20


def test_fast_path_normalises_spaced_artikelnr():
    fp = FastPathExtractor(_make_repo())
    mail = Mail(
        body="Need 06827480 ET 0001 x6 pcs",
        attachments=[],
    )
    anfrage = fp.try_extract(mail)
    assert anfrage is not None
    assert anfrage.positionen[0].artikelnummer == "06827480ET0001"
    assert anfrage.positionen[0].menge == 6.0


def test_fast_path_returns_none_on_empty_mail():
    fp = FastPathExtractor(_make_repo())
    assert fp.try_extract(Mail(body="", attachments=[])) is None


def test_fast_path_skips_when_stammdaten_empty():
    repo = InMemoryStammdatenRepository([])
    fp = FastPathExtractor(repo)
    mail = Mail(body="06827480ET0001 x6 pcs", attachments=[])
    assert fp.try_extract(mail) is None


# ------------------------------------------------------ real RFQ examples

RFQ_DIR = Path(__file__).resolve().parents[2] / "rfq_examples"


@pytest.mark.skipif(
    not (RFQ_DIR / "Request WG_ Quote.msg").exists(),
    reason="rfq_examples/ not present",
)
def test_real_rotec_msg_hits_fast_path():
    """Quote.msg: 06827480ET0001 x6 pcs — must hit fast-path."""
    from quoting.ingestion.mail import parse_mail
    fp = FastPathExtractor(_make_repo())
    mail = parse_mail(RFQ_DIR / "Request WG_ Quote.msg")
    anfrage = fp.try_extract(mail)
    assert anfrage is not None
    assert [p.artikelnummer for p in anfrage.positionen] == ["06827480ET0001"]
    assert anfrage.positionen[0].menge == 6.0


@pytest.mark.skipif(
    not (RFQ_DIR / "Request WG_ Quote Request.msg").exists(),
    reason="rfq_examples/ not present",
)
def test_real_test_fuchs_msg_hits_fast_path():
    """Quote Request.msg: 07866320ET0001, qty 3 — must hit fast-path."""
    from quoting.ingestion.mail import parse_mail
    fp = FastPathExtractor(_make_repo())
    mail = parse_mail(RFQ_DIR / "Request WG_ Quote Request.msg")
    anfrage = fp.try_extract(mail)
    assert anfrage is not None
    assert [p.artikelnummer for p in anfrage.positionen] == ["07866320ET0001"]
    assert anfrage.positionen[0].menge == 3.0


@pytest.mark.skipif(
    not (RFQ_DIR / "Request WG_ Request for Quotation erloseal.msg").exists(),
    reason="rfq_examples/ not present",
)
def test_real_volvo_msg_declines():
    """erloseal.msg: dims-only, no EK article-nr — must DECLINE."""
    from quoting.ingestion.mail import parse_mail
    fp = FastPathExtractor(_make_repo())
    mail = parse_mail(RFQ_DIR / "Request WG_ Request for Quotation erloseal.msg")
    assert fp.try_extract(mail) is None


@pytest.mark.skipif(
    not (RFQ_DIR / "Request Preisanfrage 2026-50422.pdf").exists(),
    reason="rfq_examples/ not present",
)
def test_real_preisanfrage_pdf_declines():
    """Preisanfrage PDF: customer-side part-nrs only — must DECLINE."""
    from quoting.ingestion.mail import mail_from_file
    fp = FastPathExtractor(_make_repo())
    mail = mail_from_file(RFQ_DIR / "Request Preisanfrage 2026-50422.pdf")
    assert fp.try_extract(mail) is None
