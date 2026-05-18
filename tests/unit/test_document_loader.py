"""Tests for attachment loading (CSV, Excel, PDF, images, edge cases)."""
from __future__ import annotations

import pytest

from quoting.extraction.document_loader import load_attachments


def test_empty_list_returns_empty():
    sections, images = load_attachments([])
    assert sections == []
    assert images == []


def test_missing_file_is_skipped(tmp_path):
    ghost = tmp_path / "ghost.pdf"
    sections, images = load_attachments([ghost])
    assert sections == []
    assert images == []


def test_unsupported_extension_is_skipped(tmp_path):
    f = tmp_path / "doc.docx"
    f.write_bytes(b"dummy")
    sections, images = load_attachments([f])
    assert sections == []
    assert images == []


def test_csv_semicolon_separator(tmp_path):
    f = tmp_path / "anfrage.csv"
    f.write_text("pos;artikel;menge\n10;ABC123;5\n20;DEF456;2\n", encoding="utf-8")
    sections, images = load_attachments([f])
    assert any("CSV: anfrage.csv" in s for s in sections)
    combined = "\n".join(sections)
    assert "ABC123" in combined
    assert "Row" in combined  # 0-based Row index present


def test_csv_comma_separator(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("pos,artikel,menge\n10,XYZ,100\n", encoding="utf-8")
    sections, images = load_attachments([f])
    combined = "\n".join(sections)
    assert "XYZ" in combined


def test_csv_latin1_encoding(tmp_path):
    f = tmp_path / "latin.csv"
    f.write_bytes("pos;bezeichnung\n1;Gleitst\xfcck\n".encode("latin-1"))
    sections, images = load_attachments([f])
    assert any("CSV" in s for s in sections)


def test_csv_single_column_falls_back_to_raw(tmp_path):
    f = tmp_path / "single.csv"
    f.write_text("only_one_column\nvalue1\nvalue2\n", encoding="utf-8")
    sections, images = load_attachments([f])
    # Should still add a section (raw text fallback)
    assert any("CSV" in s for s in sections)


def test_excel_single_sheet(tmp_path):
    pytest.importorskip("pandas")
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anfrage"
    ws.append(["pos_nr", "artikel", "menge"])
    ws.append([10, "001ABC", 50])
    path = tmp_path / "rfq.xlsx"
    wb.save(path)

    sections, images = load_attachments([path])
    assert any("EXCEL: rfq.xlsx" in s for s in sections)
    combined = "\n".join(sections)
    assert "001ABC" in combined
    assert "Anfrage" in combined  # sheet name present


def test_excel_multi_sheet(tmp_path):
    pytest.importorskip("pandas")
    openpyxl = pytest.importorskip("openpyxl")

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws1.append(["a", "b"])
    ws1.append([1, 2])
    ws2 = wb.create_sheet("Sheet2")
    ws2.append(["x", "y"])
    ws2.append([3, 4])
    path = tmp_path / "multi.xlsx"
    wb.save(path)

    sections, images = load_attachments([path])
    combined = "\n".join(sections)
    assert "Sheet1" in combined
    assert "Sheet2" in combined


def test_png_image_included(tmp_path):
    # Minimal 1x1 white PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    f = tmp_path / "photo.png"
    f.write_bytes(png_bytes)
    sections, images = load_attachments([f])
    assert len(images) == 1
    assert images[0]["mime_type"] == "image/png"
    assert images[0]["data"] == png_bytes
    assert images[0]["order"] == 1
    assert images[0]["label"] == "Image 1: image file photo.png"
    assert "Image 1: image file photo.png" in "\n".join(sections)


def test_jpeg_image_included(tmp_path):
    # Minimal JPEG header (not a real image but sufficient for the loader)
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 12
    f = tmp_path / "scan.jpg"
    f.write_bytes(jpeg_bytes)
    sections, images = load_attachments([f])
    assert len(images) == 1
    assert images[0]["mime_type"] == "image/jpeg"
    assert images[0]["order"] == 1
    assert images[0]["label"] == "Image 1: image file scan.jpg"


def test_multiple_images_are_labeled_in_prompt_order(tmp_path):
    png_file = tmp_path / "first.png"
    jpg_file = tmp_path / "second.jpg"
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 12
    png_file.write_bytes(png_bytes)
    jpg_file.write_bytes(jpeg_bytes)

    sections, images = load_attachments([png_file, jpg_file])

    assert [img["order"] for img in images] == [1, 2]
    assert [img["label"] for img in images] == [
        "Image 1: image file first.png",
        "Image 2: image file second.jpg",
    ]
    combined = "\n".join(sections)
    assert "=== IMAGE ORDER (VISION INPUTS) ===" in combined
    assert combined.index("Image 1: image file first.png") < combined.index(
        "Image 2: image file second.jpg"
    )


def test_pdf_pages_are_labeled_in_prompt_order(tmp_path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Page one")
    doc.new_page().insert_text((72, 72), "Page two")
    path = tmp_path / "rfq.pdf"
    doc.save(path)
    doc.close()

    sections, images = load_attachments([path])

    assert len(images) == 2
    assert [img["order"] for img in images] == [1, 2]
    assert [img["source_page"] for img in images] == [1, 2]
    assert [img["label"] for img in images] == [
        "Image 1: PDF rfq.pdf, page 1 of 2",
        "Image 2: PDF rfq.pdf, page 2 of 2",
    ]
    combined = "\n".join(sections)
    assert "=== PDF: rfq.pdf ===" in combined
    assert "=== PDF TEXT: rfq.pdf ===" in combined
    assert "Page one" in combined
    assert "Page two" in combined
    assert "Image 1: PDF rfq.pdf, page 1 of 2" in combined
    assert "Image 2: PDF rfq.pdf, page 2 of 2" in combined


def test_scanned_pdf_without_text_keeps_vision_only_sections(tmp_path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()

    sections, images = load_attachments([path])

    combined = "\n".join(sections)
    assert len(images) == 1
    assert "=== PDF: scan.pdf ===" in combined
    assert "=== PDF TEXT: scan.pdf ===" not in combined
    assert "Image 1: PDF scan.pdf, page 1 of 1" in combined


def test_multiple_attachments_all_loaded(tmp_path):
    csv_file = tmp_path / "a.csv"
    csv_file.write_text("col1;col2\nv1;v2\n", encoding="utf-8")
    csv2 = tmp_path / "b.csv"
    csv2.write_text("x;y\n1;2\n", encoding="utf-8")

    sections, images = load_attachments([csv_file, csv2])
    assert sum(1 for s in sections if "CSV:" in s) == 2
