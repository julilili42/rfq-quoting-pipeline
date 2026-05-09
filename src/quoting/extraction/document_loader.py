"""Turn attachments (PDF/XLSX/CSV/images) into prompt sections + images.

Performance notes
-----------------
PDF rasterization for vision input is the per-attachment hot path. For
multi-page RFQs (drawings + specs in one file) we now render pages in
parallel via a thread pool — PyMuPDF (fitz) releases the GIL during
``get_pixmap`` and ``tobytes`` so threading actually helps. For single-
page PDFs we skip the pool to avoid scheduling overhead.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..core import get_logger

log = get_logger()

# Cap concurrency at a reasonable bound: most RFQs are <10 pages so we
# don't need more, and we don't want to swamp small machines.
_PDF_RENDER_MAX_WORKERS = min(8, max(2, (os.cpu_count() or 2)))


def load_attachments(
    attachments: list[Path],
    dpi: int = 150,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (text_sections, image_parts) for prompt assembly."""
    sections: list[str] = []
    images: list[dict[str, Any]] = []

    for att in attachments:
        if not att.exists():
            log.warning("Attachment missing: %s", att)
            continue

        ext = att.suffix.lower().lstrip(".")
        if ext == "pdf":
            sections.append(f"=== PDF: {att.name} ===")
            images.extend(_pdf_to_images(att, dpi))
        elif ext in ("xlsx", "xls"):
            sections.append(f"=== EXCEL: {att.name} ===")
            sections.append(_excel_to_markdown(att))
        elif ext == "csv":
            sections.append(f"=== CSV: {att.name} ===")
            sections.append(_csv_to_markdown(att))
        elif ext in ("png", "jpg", "jpeg"):
            images.append(_image_to_part(att))
        else:
            log.warning("Unsupported attachment type: %s (%s)", att.name, ext)

    return sections, images


def _pdf_to_images(pdf_path: Path, dpi: int) -> list[dict[str, Any]]:
    """Render each PDF page to PNG bytes (vision input).

    Multi-page PDFs render pages in parallel via a thread pool. fitz
    releases the GIL during ``get_pixmap`` and ``tobytes`` so threading
    delivers real wall-clock wins on multi-core hardware.
    """
    import fitz  # PyMuPDF

    with fitz.open(pdf_path) as doc:
        page_count = doc.page_count

    if page_count <= 1:
        with fitz.open(pdf_path) as doc:
            pix = doc[0].get_pixmap(dpi=dpi)
            return [{"mime_type": "image/png", "data": pix.tobytes("png")}]

    # Each worker opens its own fitz.Document handle — PyMuPDF Document
    # objects are not thread-safe; sharing one across threads causes
    # sporadic SIGSEGV or corrupted pages.
    def _render(page_index: int) -> dict[str, Any]:
        with fitz.open(pdf_path) as d:
            pix = d[page_index].get_pixmap(dpi=dpi)
            return {"mime_type": "image/png", "data": pix.tobytes("png")}

    workers = min(_PDF_RENDER_MAX_WORKERS, page_count)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_render, range(page_count), timeout=120))


def _image_to_part(img_path: Path) -> dict[str, Any]:
    mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
    return {"mime_type": mime, "data": img_path.read_bytes()}


def _excel_to_markdown(xlsx_path: Path) -> str:
    """Flatten every sheet to markdown tables with 0-based Row index."""
    try:
        import pandas as pd
    except ImportError:
        return "[pandas not installed]"

    out: list[str] = []
    xls = pd.ExcelFile(xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        out.append(f"\n--- Sheet: {sheet} ---\n")
        out.append(_df_to_indexed_markdown(df))
    return "\n".join(out)


def _csv_to_markdown(csv_path: Path) -> str:
    """Parse CSV and render as markdown table with 0-based Row index."""
    try:
        import pandas as pd
    except ImportError:
        return csv_path.read_text(errors="replace")

    for sep in (";", ",", "\t", "|"):
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                df = pd.read_csv(
                    csv_path, sep=sep, encoding=enc,
                    engine="python", on_bad_lines="skip",
                )
                if len(df.columns) > 1:
                    return _df_to_indexed_markdown(df)
            except Exception:
                continue

    return csv_path.read_text(errors="replace")


def _df_to_indexed_markdown(df) -> str:
    df_idx = df.reset_index(drop=True)
    df_idx.index.name = "Row"
    return df_idx.to_markdown(index=True)
