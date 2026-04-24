"""Turn attachments (PDF/XLSX/CSV/images) into prompt sections + images."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import get_logger

log = get_logger()


def load_attachments(
    attachments: list[Path],
    dpi: int = 200,
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
            sections.append(att.read_text(errors="replace"))
        elif ext in ("png", "jpg", "jpeg"):
            images.append(_image_to_part(att))
        else:
            log.warning("Unsupported attachment type: %s (%s)", att.name, ext)

    return sections, images


def _pdf_to_images(pdf_path: Path, dpi: int) -> list[dict[str, Any]]:
    """Render each PDF page to PNG bytes (vision input)."""
    import fitz  # PyMuPDF

    parts: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            parts.append({"mime_type": "image/png", "data": pix.tobytes("png")})
    return parts


def _image_to_part(img_path: Path) -> dict[str, Any]:
    mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
    return {"mime_type": mime, "data": img_path.read_bytes()}


def _excel_to_markdown(xlsx_path: Path) -> str:
    """Flatten every sheet to markdown tables."""
    try:
        import pandas as pd
    except ImportError:
        return "[pandas not installed]"

    out: list[str] = []
    xls = pd.ExcelFile(xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        out.append(f"\n--- Sheet: {sheet} ---\n")
        out.append(df.to_markdown(index=False))
    return "\n".join(out)
