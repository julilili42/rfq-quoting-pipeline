"""Classify input files by extension."""
from __future__ import annotations

from pathlib import Path


def detect_file_type(path: Path) -> str:
    """Return 'eml' | 'pdf' | 'xlsx' | 'csv' | 'unknown'."""
    ext = path.suffix.lower().lstrip(".")
    if ext in ("eml", "msg"):
        return "eml"
    if ext == "pdf":
        return "pdf"
    if ext in ("xlsx", "xls"):
        return "xlsx"
    if ext == "csv":
        return "csv"
    return ext or "unknown"
