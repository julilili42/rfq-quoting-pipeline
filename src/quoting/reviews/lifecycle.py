"""Reset / cleanup helpers for review folders.

Both the API and the Streamlit UI used to roll their own variants of
"throw away every pipeline artifact but keep the original mail and its
attachments". This module is the single canonical implementation.

The function only touches files on disk and the approval / progress
state machines. Re-running the pipeline against the surviving mail is
the *caller's* responsibility — the API does it via ``BackgroundTasks``,
the UI does it inline. Centralising that step is harder than it sounds
because the two callers have very different execution models.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .store import saved_attachment_paths


_KEEP_FILES: set[str] = {"mail.json"}


def reset_review_artifacts(review_dir: Path, review_id: str) -> None:
    """Wipe every pipeline output but preserve the original mail.

    Specifically:

    * ``mail.json`` is preserved (the canonical input record).
    * Every attachment file referenced from ``mail.json`` is preserved.
    * Every other file or sub-folder under ``review_dir`` is deleted.
    * ``progress.json`` is re-initialised to a fresh "running" state.
    * ``approval.json`` is reset to ``draft_generated``.

    Failures during deletion are silently ignored: the next pipeline
    run will overwrite anything stale, and refusing to reset because
    one stray file is locked would only frustrate the user.
    """
    if not review_dir.exists():
        return

    keep_files: set[Path] = set()
    mail_json = review_dir / "mail.json"
    if mail_json.exists():
        keep_files.add(mail_json)
    keep_files.update(saved_attachment_paths(review_dir))

    for entry in review_dir.iterdir():
        if entry in keep_files:
            continue
        try:
            if entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
        except Exception:
            # Best-effort cleanup; the next pipeline run will overwrite.
            continue

    # Imported lazily so this module stays importable from anywhere.
    from quoting.api.approval_store import reset_approval
    from quoting.api.progress_store import init_progress

    init_progress(review_dir, review_id)
    reset_approval(review_dir)
