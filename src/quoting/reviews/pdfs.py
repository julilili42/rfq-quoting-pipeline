"""PDF lookup helpers for review artifact documents.

Every review can register one current *draft* PDF (with the red AI warning
banner) and, after approval, one current *final* PDF (without it). The
canonical filenames are::

    Angebot_Draft_{review_id}.pdf
    Angebot_{review_id}_FINAL.pdf
"""
from __future__ import annotations

from pathlib import Path

from .sqlite_repository import get_default_repository


def draft_pdf_filename(review_id: str) -> str:
    return f"Angebot_Draft_{review_id}.pdf"


def final_pdf_filename(review_id: str) -> str:
    return f"Angebot_{review_id}_FINAL.pdf"


def find_draft_pdf(review_id: str) -> Path | None:
    """Locate the draft PDF for a review, regardless of approval state."""
    return _registered_pdf(review_id, "draft_pdf")


def find_final_pdf(review_id: str) -> Path | None:
    """Locate the final (approved) PDF for a review, or ``None``."""
    return _registered_pdf(review_id, "final_pdf")


def find_current_pdf(review_id: str) -> tuple[Path | None, bool]:
    """Return ``(path, is_final)`` — final PDF if approved, else draft."""
    final = find_final_pdf(review_id)
    if final is not None:
        return final, True
    return find_draft_pdf(review_id), False


def _registered_pdf(review_id: str, kind: str) -> Path | None:
    doc = get_default_repository().current_document(review_id, kind=kind)
    if not doc:
        return None
    path = Path(str(doc.get("storage_path") or ""))
    if path.exists() and path.is_file():
        return path
    return None
