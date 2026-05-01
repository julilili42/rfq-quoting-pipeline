"""Original-input preview pane(s).

PDFs are loaded as iframes pointing at the FastAPI server's
``/api/reviews/{id}/pdf/{kind}`` endpoints. That swap (away from
inline base64 data URLs) does two things:

* Keeps the iframe payload out of the Streamlit DOM — no multi-MB
  ``<iframe src="data:application/pdf;base64,...">`` strings sitting
  in the page source.
* Gives the draft and final tabs distinct stable URLs, which fixes
  the long-standing browser conflation where both tabs would render
  identical content after approval (data URLs at the same DOM
  position were being de-duplicated by the browser).

A cache-busting query parameter is appended on every render so a
freshly-rebuilt PDF replaces the cached one immediately.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import streamlit as st

from quoting.reviews import (
    find_draft_pdf,
    find_final_pdf,
    find_current_pdf,
    pdf_url,
)


_TEXT_SUFFIXES = {".txt", ".md", ".log"}
_TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}
_MAIL_SUFFIXES = {".eml", ".msg"}


# --------------------------------------------------------------------- public
def has_real_attachment(review_input) -> bool:
    """Return True if the review carries an actual attachment."""
    if review_input is None:
        return False
    input_path: Path = review_input.input_path
    if input_path is None or not input_path.exists():
        return False
    suffix = input_path.suffix.lower()
    if suffix in _MAIL_SUFFIXES:
        return True
    if review_input.review_dir is not None:
        meta = _read_mail_meta_full(review_input.review_dir)
        if meta is not None:
            attachments = meta.get("attachments") or []
            if not attachments:
                return False
    return True


def render_input_panel(
    review_input,
    *,
    allow_mail_body_tab: bool = True,
) -> None:
    """Render the original input.

    1. Mail-only request (no real attachment) → mail body, no tabs.
    2. Mail body + real attachment, tabs allowed → two tabs, **attachment
       first**, mail body second.
    3. Otherwise → render the input file with its per-suffix renderer.
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

    if mail_body and not has_real_attachment(review_input):
        render_mail_body_pane(mail_body, mail_subject, mail_sender)
        return

    if mail_body and allow_mail_body_tab:
        file_label = _file_source_label(file_path)
        tab_file, tab_mail = st.tabs([file_label, "Mail-Text"])
        with tab_file:
            _render_input_file(file_path, payload)
        with tab_mail:
            render_mail_body_pane(mail_body, mail_subject, mail_sender)
        return

    _render_input_file(file_path, payload)


def render_input_file_only(review_input) -> None:
    """Render only the attachment (no mail-body fallback, no inner tabs).

    Used by the side-by-side comparison view, where the *outer* tab
    strip on the original side already separates file vs. mail-body.
    Avoids the visual mess of nested tabs (which was hiding CSV
    viewers in some browsers).

    Falls back to the mail body for mail-only requests so the column
    is never empty.
    """
    file_path = review_input.input_path
    payload = review_input.payload

    if (
        not has_real_attachment(review_input)
        and review_input.review_dir is not None
    ):
        body, subject, sender = _read_mail_meta(review_input.review_dir)
        if body:
            render_mail_body_pane(body, subject, sender)
            return

    _render_input_file(file_path, payload)


def render_mail_body_only(review_input) -> None:
    """Render only the mail body (used as the second tab in compare view)."""
    if review_input.review_dir is None:
        st.info("Keine Mail vorhanden — das Original ist die Datei links.")
        return
    body, subject, sender = _read_mail_meta(review_input.review_dir)
    if not body:
        st.info("Kein Mail-Text vorhanden.")
        return
    render_mail_body_pane(body, subject, sender)


def render_draft_pdf_pane() -> None:
    """Render the current PDF (legacy single-pane API).

    Prefers final PDF when the review is approved. New callers should
    use :func:`render_specific_pdf` which gives explicit control over
    draft vs. final.
    """
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        st.info("Kein Review-Verzeichnis gesetzt.")
        return

    review_dir = Path(review_dir_raw)
    review_id = st.session_state.get("review_id") or ""
    pdf, is_final = find_current_pdf(review_dir, review_id)

    if pdf is None:
        st.warning(
            "Es ist noch kein Angebotsentwurf vorhanden. "
            "Bitte zuerst zu Schritt 2 zurück, Daten bestätigen und "
            "den Auto-Refresh abwarten — oder das PDF manuell generieren.",
        )
        return

    title_prefix = "Finales Angebot" if is_final else "Angebotsentwurf"
    _render_pdf_iframe(
        review_id=review_id,
        kind="final" if is_final else "draft",
        title=f"{title_prefix} · {pdf.name}",
    )


def render_specific_pdf(*, kind: str) -> None:
    review_dir_raw = st.session_state.get("review_dir")
    if not review_dir_raw:
        st.info("Kein Review-Verzeichnis gesetzt.")
        return

    review_dir = Path(review_dir_raw)
    review_id = st.session_state.get("review_id") or ""

    if kind == "final":
        pdf = find_final_pdf(review_dir, review_id)
        if pdf is None:
            st.info(
                "Noch keine finale PDF vorhanden. "
                "Erst nach Freigabe wird sie hier angezeigt.",
            )
            return
        _render_pdf_iframe(
            review_id=review_id,
            kind="final",
            title=f"Finales Angebot · {pdf.name}",
        )
        return

    pdf = find_draft_pdf(review_dir, review_id)
    if pdf is None:
        st.warning(
            "Es ist noch kein Angebotsentwurf vorhanden. "
            "Bitte zu Schritt 2 zurück, Daten bestätigen und auf den "
            "Auto-Refresh warten — oder das PDF manuell generieren.",
        )
        return
    _render_pdf_iframe(
        review_id=review_id,
        kind="draft",
        title=f"Angebotsentwurf · {pdf.name}",
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


# ----------------------------------------------------------- PDF lookups (legacy aliases)
def find_draft_pdf_path(review_dir: Path, review_id: str) -> Path | None:
    """Back-compat wrapper around :func:`quoting.reviews.find_draft_pdf`."""
    return find_draft_pdf(review_dir, review_id)


def find_final_pdf_path(review_dir: Path, review_id: str) -> Path | None:
    """Back-compat wrapper around :func:`quoting.reviews.find_final_pdf`."""
    return find_final_pdf(review_dir, review_id)


# --------------------------------------------------------------------- per-type renderers
def _render_input_file(input_path: Path, payload: bytes) -> None:
    suffix = input_path.suffix.lower()
    if suffix == ".pdf":
        _render_input_pdf_inline(payload, title=f"Original · {input_path.name}")
    elif suffix in _TABULAR_SUFFIXES:
        _render_tabular(input_path, payload)
    elif suffix in _MAIL_SUFFIXES:
        _render_mail(input_path)
    elif suffix in _TEXT_SUFFIXES:
        _render_text(payload, title=input_path.name)
    else:
        _render_text_fallback(input_path)


def _render_pdf_iframe(*, review_id: str, kind: str, title: str) -> None:
    """Render a PDF iframe pointing at the API endpoint.

    Uses an API URL rather than an inline base64 data URL — see this
    module's docstring for why. A timestamp-based cache buster ensures
    the browser always fetches the freshest render.
    """
    src = pdf_url(review_id, kind=kind, cache_bust=True)
    title_html = _preview_title_html(title)
    shell_class = _preview_shell_class()
    st.markdown(
        (
            f'<div class="{shell_class}">'
            f'{title_html}'
            f'<iframe src="{src}" class="ek-preview-iframe" '
            f'title="{_html_escape(title)}" loading="lazy"></iframe>'
            f'</div>'
        ),
        unsafe_allow_html=True,
    )


def _render_input_pdf_inline(payload: bytes, title: str) -> None:
    """Render the *uploaded* original PDF inline.

    The original input file isn't served by the API (it's only on disk
    inside the review folder), so for the original-side panel we still
    use a base64 data URL. The conflation problem was specifically with
    *generated* draft / final PDFs in the Angebots-side compare panes,
    which is what the new API-URL approach addresses. The original
    PDF only ever renders once per page so data URLs are fine here.
    """
    import base64

    pdf_b64 = base64.b64encode(payload).decode("ascii")
    title_html = _preview_title_html(title)
    shell_class = _preview_shell_class()
    html = (
        f'<div class="{shell_class}">'
        f'{title_html}'
        f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
        f'class="ek-preview-iframe" loading="lazy"></iframe>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_tabular(input_path: Path, payload: bytes) -> None:
    """Render CSV / TSV / Excel as a DataFrame.

    Robust against the usual suspects:
    - UTF-8 BOM, latin-1 fallback
    - Comma / semicolon / tab / pipe separators (auto-picks the one
      that yields the most columns — common pitfall with German CSVs
      where ``;`` is the de-facto separator)
    - Truly broken CSVs fall through to a clear error + raw preview
    """
    suffix = input_path.suffix.lower()
    if not payload:
        st.warning(f"Datei **{input_path.name}** ist leer.")
        return

    try:
        import pandas as pd
    except ImportError:
        st.error(
            "Pandas ist nicht installiert — Tabellen können nicht "
            "gerendert werden. `pip install pandas` ausführen.",
        )
        st.code(payload[:5000].decode("utf-8", errors="replace"))
        return

    df = None
    parse_error = None
    try:
        if suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(io.BytesIO(payload))
        else:
            df = _read_csv_robust(payload, suffix, pd)
    except Exception as exc:  # noqa: BLE001
        parse_error = exc
        df = None

    if df is None or df.empty:
        st.warning(
            f"⚠️ **{input_path.name}** konnte nicht als Tabelle "
            "interpretiert werden."
            + (f" Fehler: {parse_error}" if parse_error else ""),
        )
        st.markdown("**Rohinhalt (Vorschau):**")
        st.code(payload[:5000].decode("utf-8", errors="replace"))
        return

    title_html = _preview_title_html(f"Tabelle · {input_path.name}")
    if title_html:
        st.markdown(
            f'<div class="ek-preview-shell">{title_html}</div>',
            unsafe_allow_html=True,
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Zeilen", len(df))
    c2.metric("Spalten", len(df.columns))
    c3.metric("Format", suffix.upper().lstrip("."))

    height = 740 if _is_compare_view_active() else 720
    st.dataframe(df, use_container_width=True, height=height)


def _read_csv_robust(payload: bytes, suffix: str, pd):
    """Try several separators / encodings until one yields a real table."""
    if suffix == ".tsv":
        seps = ["\t"]
    else:
        seps = [";", ",", "\t", "|"]
    encodings = ["utf-8-sig", "utf-8", "latin-1"]

    best_df = None
    best_cols = 0
    last_exc: Exception | None = None

    for enc in encodings:
        for sep in seps:
            try:
                candidate = pd.read_csv(
                    io.BytesIO(payload),
                    sep=sep,
                    encoding=enc,
                    engine="python",
                    on_bad_lines="skip",
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            cols = len(candidate.columns)
            if cols > best_cols:
                best_df = candidate
                best_cols = cols

    if best_df is not None:
        return best_df
    if last_exc is not None:
        raise last_exc
    raise ValueError("CSV could not be parsed with any separator/encoding.")


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
    """Return the preview title.

    Suppressed inside a viewer expander (the expander already names it)
    and inside the compare view (the column label / outer tab already
    name it). In compare view we still surface the *filename* portion
    of the title — that's the bit the column label doesn't carry — but
    drop the redundant ``Original ·`` / ``Angebotsentwurf ·`` prefix.
    """
    if st.session_state.get("_review_viewer_expander_active"):
        return ""
    if _is_compare_view_active():
        if " · " in title:
            _, _, name = title.partition(" · ")
            cleaned = name.strip()
            if cleaned:
                return f'<div class="ek-preview-title">{_html_escape(cleaned)}</div>'
            return ""
        return ""
    return f'<div class="ek-preview-title">{_html_escape(title)}</div>'


def _read_mail_meta(review_dir: Path) -> tuple[str | None, str, str]:
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


def _html_escape(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br/>")
    )
