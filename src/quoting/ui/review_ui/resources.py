"""Shared resources for the Streamlit review UI.

Owns the single ``QuotingPipeline`` instance the UI uses for every per-step
call. Stammdaten and the LLM client are loaded once via the pipeline; the
Streamlit-level caches sit on top so reruns are cheap.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from quoting.core import load_settings
from quoting.ingestion import Mail, detect_file_type, mail_from_file, parse_mail
from quoting.pipeline import (
    ProgressCallback,
    QuotingPipeline,
    StepContext,
    StepProgress,
)


# ---------- cached singletons ---------------------------------------------

@st.cache_resource
def settings():
    return load_settings()


@st.cache_resource
def get_pipeline() -> QuotingPipeline:
    """Single pipeline instance used by every step call from the UI."""
    return QuotingPipeline(settings())


@st.cache_resource
def stammdaten():
    """Forward to the pipeline's lazily-loaded master data."""
    return get_pipeline().stammdaten


# ---------- input helpers --------------------------------------------------

def build_mail(input_path: Path) -> Mail:
    typ = detect_file_type(input_path)
    if typ in ("eml", "msg"):
        return parse_mail(input_path)
    return mail_from_file(input_path)


@st.cache_data(show_spinner="🤖 KI extrahiert Daten...")
def extract_cached(content_hash: str, file_path: str, work_dir_str: str) -> dict:
    """Run the LLM extraction step. Cached by content hash.

    Reuses ``01_extracted.json`` from the work dir if present — that way a
    Streamlit session restart doesn't burn another LLM call on a result we
    already have on disk.
    """
    _ = content_hash  # cache key only
    work_dir = Path(work_dir_str)
    work_dir.mkdir(parents=True, exist_ok=True)

    saved = work_dir / "01_extracted.json"
    if saved.exists():
        try:
            return json.loads(saved.read_text(encoding="utf-8"))
        except Exception:
            pass  # malformed → fall through to fresh extraction

    pipeline = get_pipeline()
    mail = build_mail(Path(file_path))
    ctx = StepContext(work_dir=work_dir)
    anfrage = pipeline.extract(mail, ctx)
    return anfrage.model_dump(mode="json")


@st.cache_data
def mail_body_cached(file_path: str) -> str:
    p = Path(file_path)
    if detect_file_type(p) in ("eml", "msg"):
        return parse_mail(p).body or ""
    return ""


# ---------- progress reporting --------------------------------------------

def make_streamlit_progress(status: Any) -> ProgressCallback:
    """Bridge pipeline ``StepProgress`` events into a ``st.status`` widget.

    Each ``started`` / ``completed`` event updates the status label so the
    user sees the active step in real time. ``failed`` flips the widget to
    its error state but lets the caller handle the exception.
    """
    def callback(p: StepProgress) -> None:
        if p.status == "started":
            label = f"{p.step_name}…"
            if p.detail:
                label += f"  ({p.detail})"
            status.update(label=label, state="running")
        elif p.status == "completed":
            label = f"✓ {p.step_name}"
            if p.detail:
                label += f"  — {p.detail}"
            status.update(label=label, state="running")
        elif p.status == "failed":
            status.update(
                label=f"✗ {p.step_name}: {p.detail or 'Fehler'}",
                state="error",
            )
    return callback
