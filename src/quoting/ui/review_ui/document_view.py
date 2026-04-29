"""Original-request preview pane (left side of the review tab).

Renders whatever the user uploaded — PDF, CSV, Excel, or just the
mail body. The toggle between "Original" and "AI-Draft" used to live
inside this component; for the new 3-step flow it is opt-in via
``show_draft_toggle`` so steps 1 & 2 stay strictly focused on the
original input, and step 3 uses the new :func:`render_draft_pdf_pane`
for an explicit side-by-side comparison.

Renderers per file type:
- PDF             → inline iframe at full height
- CSV / Excel     → styled DataFrame
- Plain text/.eml → scrollable formatted block
- .eml / .msg     → mail headers + body, attachments listed below
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


_TEXT_SUFFIXES = {".txt", ".md", ".log"}
_TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}


# --------------------------------------------------------------------- public

def render_original_request(
    input_path: Path,
    payload: bytes,
    *,
    show_draft_toggle: bool = True,
) -> None:
    """Render the original input + (optional) toggle to draft PDF.

    ``show_draft_toggle`` defaults to True for backward compatibility,
    but the new step 1 / step 2 flows pass ``False`` to suppress it —
    the draft only shows up explicitly in step 3 via the comparison
    layout.
    """
    draft_pdf = _find_draft_pdf() if show_draft_toggle else None
    has_draft = draft_pdf is not None and draft_pdf.exists()

    state_key = "preview_view"
    current = st.session_state.setdefault(state_key, "original")

    _render_header(has_draft, current, state_key, input_path.name)

    if show_draft_toggle and current == "draft" and has_draft:
        _render_pdf(draft_pdf.read_bytes(), title="KI-Entwurf (Draft-Angebot)")
        return

    suffix = input_path.suffix.lower()
    if suffix == ".pdf":
        _render_pdf(payload, title=f"Original: {input_path.name}")
    elif suffix in _TABULAR_SUFFIXES:
        _render_tabular(input_path, payload)
    elif suffix in {".eml", ".msg"}:
        _render_mail(input_path)
    elif suffix in _TEXT_SUFFIXES:
        _render_text(payload)
    else:
        _render_mail_body_fallback(input_path)


def render_draft_pdf_pane() -> None:
    """Render the current draft PDF as a standalone pane.

    Used in step 3 (Vergleich & Freigabe) on the right side, next to
    the original input. The original input doesn't show the draft
    toggle in that mode — both panes are always visible.
    """
    pdf = _find_draft_pdf()
    if pdf and pdf.exists():
        _render_pdf(
            pdf.read_bytes(),
            title=f"✨ KI-Angebotsentwurf · {pdf.name}",
        )
    else:
        st.warning(
            "Es ist noch kein Angebotsentwurf vorhanden. "
            "Bitte zuerst zu Schritt 2 zurück, Daten bestätigen und "
            "den Auto-Refresh abwarten — oder das PDF manuell generieren.",
            icon="⚠️",
        )


def render_mail_body_pane(
    body: str,
    subject: str = "",
    sender: str = "",
) -> None:
    """Render a mail body directly when there are no attachments at all."""
    st.markdown(
        f"""
        <div class="ek-preview-shell">
            <div class="ek-preview-title">📧 E-Mail-Inhalt (kein Anhang)</div>
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


# --------------------------------------------------------------------- header

def _render_header(
    has_draft: bool,
    current: str,
    state_key: str,
    filename: str,
) -> None:
    if has_draft:
        col_label, col_btn1, col_btn2 = st.columns([3, 1, 1])
        with col_label:
            st.markdown(
                '<div class="ek-section-label">Vorschau · Quick-Check</div>',
                unsafe_allow_html=True,
            )
        with col_btn1:
            if st.button(
                "📄 Original",
                key=f"{state_key}_orig",
                type="primary" if current == "original" else "secondary",
                use_container_width=True,
            ):
                st.session_state[state_key] = "original"
                st.rerun()
        with col_btn2:
            if st.button(
                "✨ KI-Entwurf",
                key=f"{state_key}_draft",
                type="primary" if current == "draft" else "secondary",
                use_container_width=True,
            ):
                st.session_state[state_key] = "draft"
                st.rerun()
        st.caption(
            f"Wechsle zwischen **Original** ({filename}) und dem "
            "**KI-Entwurf** um Fehler schnell zu entdecken."
        )
    else:
        st.markdown(
            '<div class="ek-section-label">Original-Anfrage</div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------- renderers

def _render_pdf(payload: bytes, title: str) -> None:
    pdf_b64 = base64.b64encode(payload).decode()
    st.markdown(
        f"""
        <div class="ek-preview-shell">
            <div class="ek-preview-title">{title}</div>
            <iframe
                src="data:application/pdf;base64,{pdf_b64}"
                class="ek-preview-iframe"
            ></iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_tabular(input_path: Path, payload: bytes) -> None:
    """Render CSV / Excel uploads as a DataFrame with row count metric."""
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

        st.markdown(
            f"""
            <div class="ek-preview-shell">
                <div class="ek-preview-title">📊 {input_path.name}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Zeilen", len(df))
        c2.metric("Spalten", len(df.columns))
        c3.metric("Format", suffix.upper().lstrip("."))

        st.dataframe(df, use_container_width=True, height=720)
    except Exception as exc:
        st.error(f"Tabelle konnte nicht gelesen werden: {exc}")
        st.code(payload[:5000].decode("utf-8", errors="replace"))


def _render_text(payload: bytes) -> None:
    text = payload.decode("utf-8", errors="replace")
    st.markdown(
        f"""
        <div class="ek-preview-shell">
            <div class="ek-preview-title">📝 Textinhalt</div>
            <div class="ek-preview-text">{_html_escape(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_mail(input_path: Path) -> None:
    """Render a parsed .eml / .msg as headers + body."""
    try:
        from quoting.ingestion import parse_mail
        mail = parse_mail(input_path)
    except Exception as exc:
        st.error(f"Mail konnte nicht geparst werden: {exc}")
        return

    body = mail.body or "(leerer Body)"
    has_attachments = bool(mail.attachments)

    st.markdown(
        f"""
        <div class="ek-preview-shell">
            <div class="ek-preview-title">📧 E-Mail-Inhalt</div>
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
                    <span class="ek-mail-header-value">
                        {len(mail.attachments)} {'Datei' if len(mail.attachments) == 1 else 'Dateien'}
                    </span>
                </div>
            </div>
            <div class="ek-preview-text">{_html_escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if has_attachments:
        with st.expander(f"Anhänge ({len(mail.attachments)})", expanded=False):
            for att in mail.attachments:
                st.markdown(f"- `{att.name}`")


def _render_mail_body_fallback(input_path: Path) -> None:
    """Best-effort fallback: try to load as text, then as bytes."""
    try:
        text = input_path.read_text(encoding="utf-8", errors="replace")
        _render_text(text.encode("utf-8"))
    except Exception:
        st.warning(
            f"Vorschau für **{input_path.suffix.upper()}**-Dateien wird "
            "nicht unterstützt. Die Datei wird trotzdem extrahiert."
        )


# --------------------------------------------------------------------- helpers

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


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br/>")
    )
