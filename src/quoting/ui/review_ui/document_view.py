"""Original-input preview pane(s).

Three main entry points:

- :func:`render_input_panel` — renders the original input. If the
  review came from the Outlook plugin and ``mail.json`` carries a
  separate mail body alongside an attachment, both sources show up as
  tabs. When there is *only* a mail body and no attachment, the panel
  renders the mail body directly with no tabs at all.

- :func:`render_draft_pdf_pane` — renders the AI draft PDF. Used by
  step 3 next to ``render_input_panel`` for side-by-side comparison.

- :func:`has_real_attachment` — helper used by ``main.py`` to decide
  whether to show the side-by-side comparison at all. For a mail-only
  request there is nothing meaningful to put next to the draft, so
  the comparison view collapses to just the draft.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import streamlit as st


_TEXT_SUFFIXES = {".txt", ".md", ".log"}
_TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}
# Suffixes the user uploads when the review *is* a stored mail snapshot
# but the "input file" was synthesised from the mail itself.
_MAIL_SUFFIXES = {".eml", ".msg"}


# --------------------------------------------------------------------- public

def has_real_attachment(review_input) -> bool:
    """Return True if the review carries an actual attachment.

    A "real" attachment is any input file that isn't itself a synthesised
    mail-body placeholder. We use this signal to decide whether the
    side-by-side comparison view in step 3 is meaningful.
    """
    if review_input is None:
        return False

    input_path: Path = review_input.input_path
    if input_path is None or not input_path.exists():
        return False

    suffix = input_path.suffix.lower()
    if suffix in _MAIL_SUFFIXES:
        # A real .eml / .msg counts as content even though the body
        # is text — there's still an "original document" to look at.
        return True

    # Heuristic: if mail.json exists and the only attachments listed
    # are zero or unrelated to the input file, treat it as mail-only.
    if review_input.review_dir is not None:
        meta = _read_mail_meta_full(review_input.review_dir)
        if meta is not None:
            attachments = meta.get("attachments") or []
            if not attachments:
                return False

    # Otherwise the upload itself is the attachment.
    return True


def render_input_panel(
    review_input,
    *,
    allow_mail_body_tab: bool = True,
) -> None:
    """Render the original input.

    Decision tree:

    1. If the review folder has a non-empty mail body *and* a real
       attachment file → render with two tabs, mail-body first.
    2. If the review has only a mail body (no real attachment) →
       render the mail body directly with no tabs.
    3. Otherwise → render the input file with the appropriate
       per-suffix renderer.

    Pass ``allow_mail_body_tab=False`` to suppress the body tab in
    side-by-side layouts where extra height would break alignment.
    """
    file_path = review_input.input_path
    payload = review_input.payload

    mail_body, mail_subject, mail_sender = (None, "", "")
    if (
        review_input.review_dir is not None
        and file_path.suffix.lower() not in _MAIL_SUFFIXES
    ):
        mail_body, mail_subject, mail_sender = _read_mail_meta(
            review_input.review_dir,
        )

    # Mail-only request: no real attachment to render, just the body.
    if mail_body and not has_real_attachment(review_input):
        render_mail_body_pane(mail_body, mail_subject, mail_sender)
        return

    # Mail body + real attachment: tabs, mail-text *first*.
    if mail_body and allow_mail_body_tab:
        file_label = _file_source_label(file_path)
        tab_mail, tab_file = st.tabs(["Mail-Text", file_label])
        with tab_mail:
            render_mail_body_pane(mail_body, mail_subject, mail_sender)
        with tab_file:
            _render_input_file(file_path, payload)
        return

    # No mail body or tabs disabled: just the file.
    _render_input_file(file_path, payload)


def render_draft_pdf_pane() -> None:
    """Render the current draft PDF for side-by-side comparison."""
    pdf = _find_draft_pdf()
    if pdf and pdf.exists():
        _render_pdf(pdf.read_bytes(), title=f"Angebotsentwurf · {pdf.name}")
        return

    st.warning(
        "Es ist noch kein Angebotsentwurf vorhanden. "
        "Bitte zuerst zu Schritt 2 zurück, Daten bestätigen und "
        "den Auto-Refresh abwarten — oder das PDF manuell generieren.",
    )


def render_mail_body_pane(
    body: str,
    subject: str = "",
    sender: str = "",
) -> None:
    """Standalone mail-body view."""
    title_html = _preview_title_html("E-Mail-Inhalt")
    shell_class = _preview_shell_class()
    st.markdown(
        f"""
        <div class="{shell_class}">
          {title_html}
          <div class="ek-mail-headers">
            <div class="ek-mail-header-row">
              <span class="ek-mail-header-label">Betreff</span>
              <span class="ek-mail-header-value">{_html_escape(subject or "(kein Betreff)")}</span>
            </div>
            <div class="ek-mail-header-row">
              <span class="ek-mail-header-label">Von</span>
              <span class="ek-mail-header-value">{_html_escape(sender or "—")}</span>
            </div>
          </div>
          <div class="ek-preview-text">{_html_escape(body or "(leerer Body)")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------- back-compat

def render_original_request(
    input_path: Path,
    payload: bytes,
    *,
    show_draft_toggle: bool = True,
) -> None:
    """Backward-compat wrapper for the old single-source preview."""
    _ = show_draft_toggle
    _render_input_file(input_path, payload)


# --------------------------------------------------------------------- per-type renderers

def _render_input_file(input_path: Path, payload: bytes) -> None:
    suffix = input_path.suffix.lower()

    if suffix == ".pdf":
        _render_pdf(payload, title=f"Original · {input_path.name}")
    elif suffix in _TABULAR_SUFFIXES:
        _render_tabular(input_path, payload)
    elif suffix in _MAIL_SUFFIXES:
        _render_mail(input_path)
    elif suffix in _TEXT_SUFFIXES:
        _render_text(payload, title=input_path.name)
    else:
        _render_text_fallback(input_path)


def _render_pdf(payload: bytes, title: str) -> None:
    pdf_b64 = base64.b64encode(payload).decode()
    title_html = _preview_title_html(title)
    shell_class = _preview_shell_class()
    st.markdown(
        f"""
        <div class="{shell_class}">
          {title_html}
          <iframe
            src="data:application/pdf;base64,{pdf_b64}"
            class="ek-preview-iframe"
          ></iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_tabular(input_path: Path, payload: bytes) -> None:
    """Render CSV / TSV / Excel as a DataFrame with row/col counts."""
    try:
        import io
        import pandas as pd

        suffix = input_path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(io.BytesIO(payload))
        else:
            sep = "\t" if suffix == ".tsv" else ","
            try:
                df = pd.read_csv(io.BytesIO(payload), sep=sep)
            except Exception:
                df = pd.read_csv(io.BytesIO(payload), sep=";")

        title_html = _preview_title_html(f"Tabelle · {input_path.name}")
        if title_html:
            st.markdown(
                f"""
                <div class="ek-preview-shell">
                  {title_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
        c1, c2, c3 = st.columns(3)
        c1.metric("Zeilen", len(df))
        c2.metric("Spalten", len(df.columns))
        c3.metric("Format", suffix.upper().lstrip("."))
        height = 820 if _is_compare_view_active() else 720
        st.dataframe(df, use_container_width=True, height=height)
    except Exception as exc:
        st.error(f"Tabelle konnte nicht gelesen werden: {exc}")
        st.code(payload[:5000].decode("utf-8", errors="replace"))


def _render_text(payload: bytes, title: str = "Textinhalt") -> None:
    text = payload.decode("utf-8", errors="replace")
    title_html = _preview_title_html(title)
    shell_class = _preview_shell_class()
    st.markdown(
        f"""
        <div class="{shell_class}">
          {title_html}
          <div class="ek-preview-text">{_html_escape(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_mail(input_path: Path) -> None:
    """Render a parsed .eml / .msg as headers + body + attachments list."""
    try:
        from quoting.ingestion import parse_mail

        mail = parse_mail(input_path)
    except Exception as exc:
        st.error(f"Mail konnte nicht geparst werden: {exc}")
        return

    body = mail.body or "(leerer Body)"
    has_attachments = bool(mail.attachments)
    attachment_word = "Datei" if len(mail.attachments) == 1 else "Dateien"

    st.markdown(
        f"""
        <div class="{_preview_shell_class()}">
          {_preview_title_html(f"E-Mail · {input_path.name}")}
          <div class="ek-mail-headers">
            <div class="ek-mail-header-row">
              <span class="ek-mail-header-label">Betreff</span>
              <span class="ek-mail-header-value">{_html_escape(mail.subject or "(kein Betreff)")}</span>
            </div>
            <div class="ek-mail-header-row">
              <span class="ek-mail-header-label">Von</span>
              <span class="ek-mail-header-value">{_html_escape(mail.sender or "—")}</span>
            </div>
            <div class="ek-mail-header-row">
              <span class="ek-mail-header-label">Anhänge</span>
              <span class="ek-mail-header-value">{len(mail.attachments)} {attachment_word}</span>
            </div>
          </div>
          <div class="ek-preview-text">{_html_escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if has_attachments:
        if st.session_state.get("_review_viewer_expander_active"):
            st.markdown(f"**Anhänge ({len(mail.attachments)})**")
            for att in mail.attachments:
                st.markdown(f"- `{att.name}`")
        else:
            with st.expander(f"Anhänge ({len(mail.attachments)})", expanded=False):
                for att in mail.attachments:
                    st.markdown(f"- `{att.name}`")


def _render_text_fallback(input_path: Path) -> None:
    """Best-effort fallback for unknown file types."""
    try:
        text = input_path.read_text(encoding="utf-8", errors="replace")
        _render_text(text.encode("utf-8"), title=input_path.name)
    except Exception:
        st.warning(
            f"Vorschau für **{input_path.suffix.upper()}**-Dateien wird "
            "nicht unterstützt. Die Datei wird trotzdem extrahiert."
        )


# --------------------------------------------------------------------- helpers

def _is_compare_view_active() -> bool:
    return bool(st.session_state.get("_review_compare_view_active"))


def _preview_shell_class() -> str:
    classes = ["ek-preview-shell"]
    if _is_compare_view_active():
        classes.append("ek-preview-shell-compare")
    return " ".join(classes)


def _preview_title_html(title: str) -> str:
    """Return the preview title unless an outer viewer expander already names it."""
    if st.session_state.get("_review_viewer_expander_active"):
        return ""
    return f'<div class="ek-preview-title">{_html_escape(title)}</div>'


def _read_mail_meta(review_dir: Path) -> tuple[str | None, str, str]:
    """Read body/subject/from from ``mail.json`` if present."""
    path = review_dir / "mail.json"
    if not path.exists():
        return None, "", ""
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "", ""

    body = (meta.get("body") or "").strip()
    if not body:
        return None, "", ""

    subject = str(meta.get("subject") or "")
    sender = str(meta.get("from") or meta.get("sender") or "")
    return body, subject, sender


def _read_mail_meta_full(review_dir: Path) -> dict | None:
    path = review_dir / "mail.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _file_source_label(input_path: Path) -> str:
    """Human-friendly tab label for a file."""
    suffix = input_path.suffix.upper().lstrip(".")
    name = input_path.name
    if not suffix:
        return name
    return f"{suffix} · {name}"


def _find_draft_pdf() -> Path | None:
    """Locate the AI-generated draft PDF for the current review."""
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        return None
    review_dir = Path(review_dir_raw)
    review_id = st.session_state.get("review_id") or ""

    candidates: list[Path] = []
    if review_id:
        candidates.append(review_dir / f"Angebot_Draft_{review_id}.pdf")
    candidates.append(review_dir / "draft_angebot.pdf")
    candidates.extend(sorted(review_dir.rglob("*_ANGEBOT_DRAFT.pdf")))
    candidates.extend(sorted(review_dir.rglob("*_ANGEBOT_FINAL.pdf")))

    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _html_escape(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br/>")
    )
