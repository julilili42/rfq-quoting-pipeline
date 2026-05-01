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


# ------------------------------------------------------------------ generic
def read_json(path: Path) -> Any:
    """Return parsed JSON or ``None`` on missing / malformed input."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, value: Any) -> None:
    """Atomically serialize ``value`` to ``path`` as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_to_jsonable(value), indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------- review-aware
def load_mail_meta(review_dir: Path) -> dict | None:
    """Return the parsed ``mail.json`` for a review, if present."""
    return read_json(review_dir / "mail.json")


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
    return read_json(review_dir / "review_state.json")


# ------------------------------------------------------------------ internal
def _to_jsonable(value: Any) -> Any:
    """Best-effort conversion of common types into JSON-ready primitives."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value
