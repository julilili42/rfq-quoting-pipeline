from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st


def read_review_progress(review_dir: Path) -> dict[str, Any] | None:
    path = review_dir / "progress.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_review_processing(progress: dict[str, Any] | None) -> bool:
    if not progress:
        return False
    return progress.get("status") == "running"


def is_review_failed(progress: dict[str, Any] | None) -> bool:
    if not progress:
        return False
    return progress.get("status") == "failed"


def render_pipeline_progress(progress: dict[str, Any]) -> None:
    status = progress.get("status", "running")
    current_step = progress.get("current_step", "Pipeline")
    current_detail = progress.get("current_detail", "")
    percent = int(progress.get("progress_percent") or 0)
    steps = progress.get("steps") or []

    st.markdown(
        '<div class="ek-section-label">Pipeline-Status</div>',
        unsafe_allow_html=True,
    )

    if status == "failed":
        st.error(
            f"Pipeline fehlgeschlagen bei **{current_step}**: "
            f"{progress.get('error') or current_detail or 'Unbekannter Fehler'}",
        )
    elif status == "completed":
        st.success("Pipeline abgeschlossen. Review ist bereit.")
    else:
        st.info(
            f"Aktueller Schritt: **{current_step}**"
            + (f" — {current_detail}" if current_detail else ""),
        )

    st.progress(percent / 100)

    for step in steps:
        name = step.get("name", "Unbekannter Schritt")
        step_status = step.get("status", "pending")
        detail = step.get("detail", "")

        label = {
            "completed": "Erledigt",
            "running": "Läuft",
            "failed": "Fehler",
            "skipped": "Übersprungen",
            "pending": "Offen",
        }.get(step_status, step_status)

        with st.container(border=True):
            st.markdown(f"**{name}** · {label}")
            if detail:
                st.caption(detail)

    st.caption(
        "Diese Ansicht liest den Pipeline-Status aus `progress.json`. "
        "Aktualisiere die Seite, um den neuesten Stand zu sehen."
    )
    if st.button("Status aktualisieren", type="primary"):
        st.rerun()
