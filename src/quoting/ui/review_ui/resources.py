from __future__ import annotations

from pathlib import Path

import streamlit as st

from quoting.core import load_settings
from quoting.extraction import extract_anfrage
from quoting.ingestion import Mail, detect_file_type, mail_from_file, parse_mail
from quoting.matching import load_stammdaten


@st.cache_resource
def settings():
    return load_settings()


@st.cache_resource
def stammdaten():
    return load_stammdaten(settings().stammdaten_path)


def build_mail(input_path: Path) -> Mail:
    typ = detect_file_type(input_path)

    if typ in ("eml", "msg"):
        return parse_mail(input_path)

    return mail_from_file(input_path)


@st.cache_data(show_spinner="🤖 KI extrahiert Daten...")
def extract_cached(content_hash: str, file_path: str) -> dict:
    """Extract Anfrage from a Mail built from file_path. Cached by content_hash."""
    _ = content_hash

    mail = build_mail(Path(file_path))
    anfrage = extract_anfrage(mail.attachments, mail.body, settings())

    return anfrage.model_dump(mode="json")


@st.cache_data
def mail_body_cached(file_path: str) -> str:
    p = Path(file_path)

    if detect_file_type(p) in ("eml", "msg"):
        return parse_mail(p).body or ""

    return ""