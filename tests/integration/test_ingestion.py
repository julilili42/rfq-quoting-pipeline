"""Smoke test for file-type detection — no LLM, no external data."""
from pathlib import Path

from quoting.ingestion import detect_file_type


def test_detects_pdf():
    assert detect_file_type(Path("foo.pdf")) == "pdf"


def test_detects_eml():
    assert detect_file_type(Path("mail.eml")) == "eml"
    assert detect_file_type(Path("legacy.msg")) == "eml"


def test_detects_excel():
    assert detect_file_type(Path("sheet.xlsx")) == "xlsx"
    assert detect_file_type(Path("sheet.xls")) == "xlsx"


def test_detects_csv():
    assert detect_file_type(Path("data.csv")) == "csv"


def test_unknown_extension():
    assert detect_file_type(Path("weird.xyz")) == "xyz"


def test_uppercase_extension_normalized():
    assert detect_file_type(Path("FOO.PDF")) == "pdf"
