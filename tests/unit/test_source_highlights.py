from __future__ import annotations

from pathlib import Path

import pytest

from quoting.reviews.source_highlights import resolve_pdf_highlight

fitz = pytest.importorskip("fitz")


def _write_pdf(path: Path, lines: list[tuple[float, float, str]]) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=10)
    doc.save(path)
    doc.close()
    return path


def test_candidate_article_number_marks_position_block(tmp_path: Path):
    pdf = _write_pdf(
        tmp_path / "rfq.pdf",
        [
            (60, 100, "Pos. Artikelnr. Bezeichnung Menge"),
            (60, 140, "1 001GLP108015 Gleitstueck fuer Wiegentraeger 100 Stueck"),
            (60, 180, "2 002GLS082003 Gleitstueck 50 Stueck"),
        ],
    )

    result = resolve_pdf_highlight(
        pdf,
        source_page=1,
        source_quote="not an exact PDF quote",
        candidates=["001GLP108015"],
        target_kind="position",
    )

    assert result.status == "block"
    assert result.pageIndex == 0
    assert len(result.areas) == 1
    assert result.areas[0].left < 12
    assert result.areas[0].width > 30


def test_header_value_candidate_marks_value(tmp_path: Path):
    pdf = _write_pdf(
        tmp_path / "rfq.pdf",
        [
            (60, 100, "Belegnummer"),
            (180, 100, "2026-50422"),
        ],
    )

    result = resolve_pdf_highlight(
        pdf,
        source_page=1,
        source_quote=None,
        candidates=["2026-50422"],
        target_kind="header",
    )

    assert result.status == "candidate"
    assert result.pageIndex == 0
    assert len(result.areas) == 1


def test_email_quote_prefers_address_over_generic_label(tmp_path: Path):
    pdf = _write_pdf(
        tmp_path / "rfq.pdf",
        [
            (60, 100, "Email f.hochstein@goehmann.com"),
            (60, 130, "Kontakt info@goehmann.com"),
        ],
    )

    result = resolve_pdf_highlight(
        pdf,
        source_page=1,
        source_quote="Email info@goehmann.com",
        candidates=[],
        target_kind="header",
    )

    assert result.status == "candidate"
    assert result.matched_text == "info@goehmann.com"
    assert len(result.areas) == 1


def test_long_quote_falls_back_to_token(tmp_path: Path):
    pdf = _write_pdf(
        tmp_path / "rfq.pdf",
        [(60, 140, "1 001APZ00031B Abnahmezeugnis nach DIN EN 10204 1 Stueck")],
    )
    quote = " ".join(["LLM paraphrased this position"] * 10) + " 001APZ00031B"

    result = resolve_pdf_highlight(
        pdf,
        source_page=1,
        source_quote=quote,
        target_kind="position",
    )

    assert result.status == "block"
    assert result.matched_text == "001APZ00031B"


def test_pdf_without_text_layer_returns_page_only(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(pdf)
    doc.close()

    result = resolve_pdf_highlight(
        pdf,
        source_page=1,
        source_quote="001GLP108015",
        candidates=["001GLP108015"],
        target_kind="position",
    )

    assert result.status == "page_only"
    assert result.pageIndex == 0
    assert result.areas == []


def test_no_match_without_source_page_returns_not_found(tmp_path: Path):
    pdf = _write_pdf(tmp_path / "rfq.pdf", [(60, 100, "No matching content")])

    result = resolve_pdf_highlight(
        pdf,
        source_quote="001GLP108015",
        candidates=["001GLP108015"],
        target_kind="position",
    )

    assert result.status == "not_found"
    assert result.pageIndex is None
