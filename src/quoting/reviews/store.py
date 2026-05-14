"""Disk-level helpers for review folders.

Review folders carry a small set of JSON sidecars (``mail.json``,
``approval.json``, ``progress.json``, ``manual_overrides.json``,
``review_state.json``, …). The functions here own the boring file I/O
so callers can focus on the data.

Conventions
-----------
- Reads are tolerant: a missing or malformed file returns ``None``
  rather than raising. Callers decide what "missing" means in context.
- Writes are atomic: ``write_json`` writes to a ``.tmp`` sibling and
  renames into place. Concurrent readers therefore see either the old
  file or the new one — never a half-written one.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


# ------------------------------------------------------------------ filenames
class ReviewFiles:
    """Canonical names of the JSON sidecars in a review folder.

    Centralized so a rename only touches this class. The names are
    persisted on disk for existing reviews, so don't change them lightly.
    """

    MAIL = "mail.json"
    APPROVAL = "approval.json"
    PROGRESS = "progress.json"
    ANFRAGE_REVIEWED = "anfrage_reviewed.json"
    EXTRACTED = "01_extracted.json"
    MATCHES_REVIEWED = "matches_reviewed.json"
    MANUAL_OVERRIDES = "manual_overrides.json"
    QUOTATION_REVIEWED = "quotation_reviewed.json"


# ------------------------------------------------------------------ generic
def read_json(path: Path) -> Any:
    """Return parsed JSON or ``None`` on missing / malformed input."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def read_json_list(path: Path) -> list:
    """Return parsed JSON as a list, or ``[]`` if missing / malformed / wrong shape."""
    data = read_json(path)
    return data if isinstance(data, list) else []


def write_json(path: Path, value: Any) -> None:
    """Atomically serialize ``value`` to ``path`` as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_to_jsonable(value), indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------- review-aware
def load_mail_meta(review_dir: Path) -> dict | None:
    """Return the parsed ``mail.json`` for a review, if present."""
    return read_json(review_dir / ReviewFiles.MAIL)


def saved_attachment_paths(review_dir: Path) -> set[Path]:
    """Return the set of attachment files persisted alongside ``mail.json``.

    Used by the reset/cleanup logic to know which files in the review
    folder must survive a pipeline restart.
    """
    meta = load_mail_meta(review_dir)
    if not isinstance(meta, dict):
        return set()
    out: set[Path] = set()
    for entry in meta.get("attachments") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        out.add(review_dir / Path(name).name)
    return out


def load_review_state(review_dir: Path) -> dict | None:
    """Return the parsed ``review_state.json`` snapshot, if present."""
    return read_json(review_dir / "review_state.json")  # not in ReviewFiles — Streamlit-era artifact


# ------------------------------------------------------------------ internal
_MAX_JSONABLE_DEPTH = 50


def _to_jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of common types into JSON-ready primitives."""
    if _depth > _MAX_JSONABLE_DEPTH:
        raise ValueError(f"_to_jsonable exceeded max depth ({_MAX_JSONABLE_DEPTH}): possible circular reference")
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(item, _depth + 1) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item, _depth + 1) for key, item in value.items()}
    return value
