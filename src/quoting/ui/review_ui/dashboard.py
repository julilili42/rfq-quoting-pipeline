"""Dashboard — landing page for the Streamlit review UI.

Shows every review on disk with its current status, plus value-oriented
statistics (extraction quality, match rate, time saved). Each row links
into the review detail via ``?review_id=…``.

Layout
------
- Hero
- KPI strip (always visible — the headline numbers)
- **Insights** (collapsible, expanded by default on first visit)
- Reviews list (compact rows, paginated)
"""
from __future__ import annotations

from base64 import b64encode
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from quoting.ui.review_ui.review_loader import ReviewSummary, scan_reviews

# Conservative estimate: how long would a human take to do one review by
# hand. Used only for the "time saved" headline.
MINUTES_PER_MANUAL_REVIEW = 15

PAGE_SIZE = 12

_STATUS_LABEL = {
    "abgeschlossen": "Abgeschlossen",
    "pdf_bereit":    "PDF bereit",
    "in_arbeit":     "In Arbeit",
}

_STATUS_PILL_CLASS = {
    "abgeschlossen": "ek-pill ek-pill-success",
    "pdf_bereit":    "ek-pill ek-pill-info",
    "in_arbeit":     "ek-pill ek-pill-warning",
}


# ---------------------------------------------------------------- entry point

def render_dashboard(reviews_root: Path) -> None:
    """Top-level dashboard renderer."""
    summaries = scan_reviews(reviews_root)

    _render_hero()

    if not summaries:
        _render_empty_state()
        return

    st.markdown("&nbsp;", unsafe_allow_html=True)

    with st.expander("📊 Insights anzeigen", expanded=False):
        _render_value_metrics(summaries)
        st.markdown("&nbsp;", unsafe_allow_html=True)
        _render_insights(summaries)

    st.markdown("---")
    _render_filters_and_list(summaries)


# ------------------------------------------------------------------- hero

def _render_hero() -> None:
    st.markdown(
        """
        <div class="ek-title-block">
          <h1 class="ek-title">
            Quoting-Übersicht<span class="ek-accent-dot">.</span>
          </h1>
          <p class="ek-subtitle">
            Alle Anfragen, die durch die KI-Pipeline gelaufen sind —
            inklusive Status, Match-Qualität und Bearbeitungsverlauf.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_state() -> None:
    st.info(
        "Noch keine Reviews vorhanden. Sobald aus Outlook eine Anfrage "
        "an die Review-API gesendet wird, erscheint sie hier — "
        "alternativ links eine Datei hochladen und ein Angebot manuell "
        "generieren.",
        icon="📭",
    )


# ------------------------------------------------------------------- metrics

def _render_value_metrics(summaries: list[ReviewSummary]) -> None:
    """Headline KPIs that show *operational* value of the solution."""
    total = len(summaries)
    avg_positions = (
        sum(s.positions for s in summaries) / total if total else 0
    )
    matched = sum(s.matched for s in summaries)
    total_positions = sum(s.positions for s in summaries)
    avg_match_rate = matched / total_positions if total_positions else 0.0

    minutes_saved = total * MINUTES_PER_MANUAL_REVIEW
    hours_saved = minutes_saved / 60

    st.markdown(
        '<div class="ek-section-label">Operative Wirkung</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Reviews bearbeitet",
        f"{total}",
        help="Gesamtanzahl der Anfragen, die durch die Pipeline gelaufen sind.",
    )
    c2.metric(
        "Ø Positionen",
        f"{avg_positions:.1f}",
        help="Durchschnittliche Anzahl Positionen pro Anfrage.",
    )
    c3.metric(
        "Ø Match-Quote",
        f"{avg_match_rate:.0%}",
        help=(
            "Anteil aller Positionen, für die ein Stammdaten-Treffer "
            "gefunden wurde — weniger manuelle Suche."
        ),
    )
    c4.metric(
        "Geschätzte Zeitersparnis",
        f"{hours_saved:.1f} h",
        help=(
            f"Annahme: ~{MINUTES_PER_MANUAL_REVIEW} Min pro Anfrage "
            "manuell. Konservativ geschätzt."
        ),
    )


# ------------------------------------------------------------------ list view

def _render_filters_and_list(summaries: list[ReviewSummary]) -> None:
    st.markdown(
        '<div class="ek-section-label">Reviews</div>',
        unsafe_allow_html=True,
    )

    col_filter, _, col_search = st.columns([2, 1, 2])
    with col_filter:
        status_filter = st.radio(
            "Status",
            options=["Alle", "In Arbeit", "PDF bereit", "Abgeschlossen"],
            horizontal=True,
            label_visibility="collapsed",
        )
    with col_search:
        query = st.text_input(
            "Suche",
            placeholder="🔍 Betreff oder Absender…",
            label_visibility="collapsed",
        )

    filtered = _apply_filters(summaries, status_filter, query)

    if not filtered:
        st.caption(f"Keine Reviews mit Filter „{status_filter}“ gefunden.")
        return

    # Pagination
    total = len(filtered)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page_key = f"_dashboard_page_{status_filter}_{query}"
    current_page = int(st.session_state.get(page_key, 1))
    current_page = max(1, min(current_page, page_count))

    start = (current_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = filtered[start:end]

    st.caption(
        f"{start + 1}–{min(end, total)} von {total} Reviews "
        f"(Seite {current_page} von {page_count})"
    )

    for s in page_items:
        _render_review_row(s)

    if page_count > 1:
        _render_pagination(page_key, current_page, page_count)


def _apply_filters(
    summaries: list[ReviewSummary],
    status_filter: str,
    query: str,
) -> list[ReviewSummary]:
    target = {
        "Alle": None,
        "In Arbeit": "in_arbeit",
        "PDF bereit": "pdf_bereit",
        "Abgeschlossen": "abgeschlossen",
    }.get(status_filter)

    q = (query or "").strip().lower()

    out = []
    for s in summaries:
        if target and s.status != target:
            continue
        if q and q not in s.subject.lower() and q not in s.sender.lower():
            continue
        out.append(s)
    return out


def _render_review_row(s: ReviewSummary) -> None:
    """One review as a compact card with inline actions."""
    overrides_marker = (
        f' · ✏️ {s.manual_overrides_count} '
        f'{"Anpassung" if s.manual_overrides_count == 1 else "Anpassungen"}'
        if s.manual_overrides_count
        else ""
    )
    pdf_marker = " · 📄 PDF" if s.pdf_path else ""
    pdf_action = _pdf_download_action(s)
    open_href = f"?review_id={quote(s.review_id, safe='')}"

    st.markdown(
        f"""
        <div class="ek-review-card">
          <a class="ek-review-card-link"
             href="{open_href}"
             target="_self"
             aria-label="Review {_safe_html(s.review_id)} öffnen"></a>
          <div class="ek-review-main">
            <div class="ek-review-head-row">
              <span class="{_STATUS_PILL_CLASS[s.status]}">
                <span class="ek-pill-dot"></span>{_STATUS_LABEL[s.status]}
              </span>
              <code class="ek-review-id">{_safe_html(s.review_id)}</code>
            </div>
            <div class="ek-review-subject">{_safe_html(s.subject)}</div>
            <div class="ek-review-meta">
              {_safe_html(s.sender) or "—"}
              · {s.positions} Pos · Match {s.match_rate:.0%}
              · {s.total_eur:,.2f} {s.currency}{pdf_marker}{overrides_marker}
            </div>
          </div>
          <div class="ek-review-actions">
            <span class="ek-review-date">{_format_date(s.updated_at)}</span>
            {pdf_action}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pagination(page_key: str, current: int, total: int) -> None:
    """Compact page navigator: ‹ Prev · 1 / N · Next ›."""
    cols = st.columns([1, 1, 1, 1, 1])
    with cols[1]:
        if st.button(
            "← Zurück",
            key=f"{page_key}_prev",
            disabled=current <= 1,
            use_container_width=True,
        ):
            st.session_state[page_key] = current - 1
            st.rerun()
    with cols[2]:
        st.markdown(
            f'<div style="text-align:center;padding-top:6px;color:var(--ek-muted);'
            f'font-weight:600;">Seite {current} / {total}</div>',
            unsafe_allow_html=True,
        )
    with cols[3]:
        if st.button(
            "Weiter →",
            key=f"{page_key}_next",
            disabled=current >= total,
            use_container_width=True,
        ):
            st.session_state[page_key] = current + 1
            st.rerun()


# ------------------------------------------------------------------ insights

def _render_insights(summaries: list[ReviewSummary]) -> None:
    """Charts + extraction-quality breakdown. Lives inside the top expander."""
    total_positions = sum(s.positions for s in summaries) or 1

    st.markdown("**Extraktions-Qualität (KI-Konfidenz)**")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "Konfidenz hoch",
        f"{sum(s.confidence_high for s in summaries) / total_positions:.0%}",
        help="Anteil Positionen, die das Modell mit hoher Sicherheit extrahiert hat.",
    )
    c6.metric(
        "Konfidenz mittel",
        sum(s.confidence_medium for s in summaries),
    )
    c7.metric(
        "Konfidenz gering",
        sum(s.confidence_low for s in summaries),
    )
    c8.metric(
        "Kein Stammdaten-Treffer",
        sum(s.matches_no_match for s in summaries),
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Match-Verteilung**")
        match_breakdown = {
            "Exakt":          sum(s.matches_exact for s in summaries),
            "Fuzzy":          sum(s.matches_fuzzy for s in summaries),
            "Semantisch":     sum(s.matches_semantic for s in summaries),
            "Kein Treffer":   sum(s.matches_no_match for s in summaries),
        }
        st.bar_chart(match_breakdown, height=220)

    with col_b:
        st.markdown("**KI-Konfidenz**")
        conf_breakdown = {
            "Hoch":   sum(s.confidence_high for s in summaries),
            "Mittel": sum(s.confidence_medium for s in summaries),
            "Gering": sum(s.confidence_low for s in summaries),
        }
        st.bar_chart(conf_breakdown, height=220)

    article_counter: Counter[str] = Counter()
    for s in summaries:
        for art in s.extracted_articles:
            if art:
                article_counter[art] += 1
    top = article_counter.most_common(10)

    if top:
        st.markdown("**Häufigste angefragte Artikel**")
        st.dataframe(
            [{"Artikel-Nr.": a, "Anfragen": n} for a, n in top],
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------------ helpers

def _format_date(dt: datetime) -> str:
    if dt.year < 2000:
        return "—"
    return dt.strftime("%d.%m.%Y · %H:%M")


def _safe_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pdf_download_action(s: ReviewSummary) -> str:
    if not s.pdf_path or not s.pdf_path.exists():
        return ""

    encoded = b64encode(s.pdf_path.read_bytes()).decode("ascii")
    filename = _safe_html(s.pdf_path.name)
    return (
        '<a class="ek-review-action ek-review-action-download" '
        f'href="data:application/pdf;base64,{encoded}" '
        f'download="{filename}" '
        f'aria-label="PDF {filename} herunterladen">PDF herunterladen</a>'
    )
