"""Per-review actions invoked from the sidebar.

Currently exposes a single action — *Pipeline neu starten* — but the
file is structured so future actions (export, archive, force-close)
can sit next to it without bloating ``main.py``.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.ingestion import Mail
from quoting.reviews import (
    load_mail_meta,
    reset_review_artifacts,
)
from quoting.ui.review_ui.resources import get_pipeline
from quoting.ui.review_ui.state import reset_review_state


def reset_pipeline(review_dir: Path, review_id: str) -> None:
    """Reset a review folder to a clean slate and re-run the pipeline.

    The cleanup of files on disk + approval / progress reset lives in
    :func:`quoting.reviews.reset_review_artifacts`. This function adds
    the Streamlit-specific bits: clearing session state, rebuilding
    a ``Mail`` from the persisted ``mail.json`` and triggering a
    fresh pipeline run inline.
    """
    if not review_dir.exists():
        st.error("Review-Verzeichnis nicht mehr verfügbar.")
        return

    reset_review_artifacts(review_dir, review_id)
    reset_review_state()
    st.session_state.pop("_matches_cache", None)

    try:
        mail = _rebuild_mail(review_dir)
        if mail is None:
            st.error(
                "Pipeline-Reset fehlgeschlagen: keine Mail-Metadaten "
                "auf der Platte gefunden.",
            )
            return
        get_pipeline().run(
            mail,
            output_dir=review_dir.parent,
            work_name=review_id,
        )
    except Exception as exc:
        st.error(f"Pipeline-Reset fehlgeschlagen: {exc}")
        return

    st.success("Pipeline wurde neu ausgeführt.")
    st.rerun()


def _rebuild_mail(review_dir: Path) -> Mail | None:
    meta = load_mail_meta(review_dir)
    if not isinstance(meta, dict):
        return None

    attachments = []
    for att in meta.get("attachments") or []:
        if isinstance(att, dict) and att.get("name"):
            p = review_dir / att["name"]
            if p.exists():
                attachments.append(p)

    return Mail(
        subject=meta.get("subject", ""),
        sender=meta.get("from") or meta.get("sender", ""),
        body=meta.get("body", ""),
        attachments=attachments,
    )
