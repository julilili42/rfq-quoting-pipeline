"""PDF lookup helpers for review folders.

Every review folder contains at most one *draft* PDF (with the red AI
warning banner) and, after approval, one *final* PDF (without it).
The naming convention is::

    Angebot_Draft_{review_id}.pdf
    Angebot_{review_id}_FINAL.pdf

For backwards compatibility we also accept the older legacy names
(``draft_angebot.pdf``, ``final_angebot.pdf``, ``*_ANGEBOT_DRAFT.pdf``)
and the explicit ``approval.final_pdf_path`` pointer that the approval
state machine writes when the user clicks "Freigeben".
"""
from __future__ import annotations

from pathlib import Path


def draft_pdf_filename(review_id: str) -> str:
    """Canonical filename for the draft PDF of a review."""
    return f"Angebot_Draft_{review_id}.pdf"


def final_pdf_filename(review_id: str) -> str:
    """Canonical filename for the final (approved) PDF of a review."""
    return f"Angebot_{review_id}_FINAL.pdf"


def find_draft_pdf(review_dir: Path, review_id: str | None = None) -> Path | None:
    """Locate the draft PDF for a review, regardless of approval state.

    The draft PDF carries the red AI warning banner and is the artifact
    the reviewer corrects. Returned even after approval so the
    side-by-side compare view can still display it.
    """
    candidates: list[Path] = []
    if review_id:
        candidates.append(review_dir / draft_pdf_filename(review_id))
    candidates.append(review_dir / "draft_angebot.pdf")
    candidates.extend(sorted(review_dir.glob("*_ANGEBOT_DRAFT.pdf")))
    candidates.extend(sorted(review_dir.glob("*/*_ANGEBOT_DRAFT.pdf")))
    return _first_existing(candidates)


def find_final_pdf(review_dir: Path, review_id: str | None = None) -> Path | None:
    """Locate the final (approved) PDF for a review.

    Resolution order:

    1. ``approval.json``'s ``final_pdf_path`` pointer — the canonical
       reference written when the user explicitly approves the review.
    2. The conventional ``Angebot_{review_id}_FINAL.pdf`` filename.
    3. Legacy ``final_angebot.pdf`` / ``*_FINAL.pdf`` patterns.

    Returns ``None`` if no final PDF has been produced yet.
    """
    pointer = _final_path_from_approval(review_dir)
    if pointer is not None and pointer.exists():
        return pointer

    candidates: list[Path] = []
    if review_id:
        candidates.append(review_dir / final_pdf_filename(review_id))
    candidates.append(review_dir / "final_angebot.pdf")
    candidates.extend(sorted(review_dir.glob("*_ANGEBOT_FINAL.pdf")))
    candidates.extend(sorted(review_dir.glob("*_FINAL.pdf")))
    return _first_existing(candidates)


def find_current_pdf(
    review_dir: Path,
    review_id: str | None = None,
) -> tuple[Path | None, bool]:
    """Return ``(path, is_final)`` — final PDF if approved, else draft.

    Used by the legacy single-pane viewer; new code should prefer the
    explicit ``find_draft_pdf`` / ``find_final_pdf`` pair.
    """
    final = find_final_pdf(review_dir, review_id)
    if final is not None:
        return final, True
    draft = find_draft_pdf(review_dir, review_id)
    return draft, False


# ----------------------------------------------------------------- internals
def _first_existing(paths: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists() and path.is_file():
            return path
    return None


def _final_path_from_approval(review_dir: Path) -> Path | None:
    """Read ``approval.json`` and return ``final_pdf_path`` if approved.

    Imports are deferred so the ``reviews`` package stays importable
    in places that don't (yet) have the API package available.
    """
    try:
        from quoting.api.approval_store import load_approval
    except Exception:
        return None
    try:
        record = load_approval(review_dir)
    except Exception:
        return None
    if record.state not in ("approved", "ready_to_send"):
        return None
    if not record.final_pdf_path:
        return None
    return review_dir / record.final_pdf_path
