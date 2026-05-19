"""Reset / cleanup helpers for reviews.

Review state lives in SQLite. The artifact directory only contains
binary files such as uploaded originals and generated PDFs; reset keeps
the originals, drops generated artifacts from disk, and clears derived
database payloads.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..core import get_logger
from .sqlite_repository import Payloads, get_default_repository

log = get_logger()


def reset_review_artifacts(review_id: str) -> None:
    """Wipe pipeline outputs while preserving uploaded originals."""
    repo = get_default_repository()
    folder = repo.artifact_dir(review_id)

    keep_files = _registered_original_paths(review_id)
    if folder.exists():
        for entry in folder.iterdir():
            if entry in keep_files:
                continue
            try:
                if entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)
            except Exception as exc:
                log.warning("Could not delete %s during reset: %s", entry, exc)

    repo.reset_review_state(review_id, keep={Payloads.MAIL})
    repo.delete_documents_except(review_id, keep_kinds={"attachment", "original"})

    # Imported lazily so this module stays importable from anywhere.
    from quoting.api.approval_store import reset_approval
    from quoting.api.progress_store import init_progress

    init_progress(review_id)
    reset_approval(review_id)


def _registered_original_paths(review_id: str) -> set[Path]:
    repo = get_default_repository()
    keep: set[Path] = set()
    for kind in ("attachment", "original"):
        for doc in repo.list_documents(review_id, kind=kind):
            path = Path(str(doc.get("storage_path") or ""))
            if path.name:
                keep.add(path)
    return keep
