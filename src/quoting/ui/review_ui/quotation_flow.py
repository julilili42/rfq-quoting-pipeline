"""Per-review quotation flow — pricing, rendering, persistence.

Sits on top of the pipeline's per-step API. The only thing that's *not*
a pipeline step is the manual-override layer between pricing and
rendering, because it's a UI-specific concept (the chat agent's
human-in-the-loop edits).

This module also exposes ``finalize_pdf()`` which the approval panel
calls to re-render the PDF *without* the AI-warning banner.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
import tempfile

import streamlit as st

from quoting.core import Anfrage
from quoting.pipeline import StepContext
from quoting.pricing import Quotation, QuotationItem
from quoting.reviews import (
    draft_pdf_filename,
    final_pdf_filename,
    find_draft_pdf,
    read_json,
    write_json,
)
from quoting.ui.review_agent import apply_manual_overrides, build_agent_summary
from quoting.ui.review_ui.resources import get_pipeline, make_streamlit_progress
from quoting.ui.review_ui.state import safe_file_stub


def _resolve_company_profile():
    """Pick the right CompanyProfile for the current render.

    Defers the import of the editor's helper so tests that don't load
    Streamlit context don't blow up. The editor stores per-review
    overrides on session state; the helper merges them with the saved
    settings profile.
    """
    try:
        from quoting.ui.review_ui.editor import get_effective_company_profile
        return get_effective_company_profile()
    except Exception:
        from quoting.api.settings_store import load_user_settings
        return load_user_settings().company


# ---------- state hydration -----------------------------------------------
def hydrate_existing_review_state(content_hash: str, matches) -> None:
    """Reload a previously-saved quotation/PDF from disk into session state."""
    review_dir_raw = st.session_state.get("review_dir")
    review_id = st.session_state.get("review_id")
    if not review_dir_raw:
        return
    if (
        st.session_state.get("quotation_hash") == content_hash
        and st.session_state.get("quotation")
    ):
        return

    review_dir = Path(review_dir_raw)

    overrides = read_json(review_dir / "manual_overrides.json")
    if isinstance(overrides, list):
        st.session_state["manual_discount_overrides"] = overrides
    else:
        overrides = []

    quotation = _load_saved_quotation(review_dir)
    if quotation:
        st.session_state["quotation"] = quotation
        st.session_state["quotation_hash"] = content_hash
        st.session_state["pdf_file_name"] = (
            f"Angebot_Draft_{review_id or content_hash}.pdf"
        )
        pdf_path = find_draft_pdf(review_dir, review_id)
        if pdf_path and pdf_path.exists():
            st.session_state["generated_pdf_path"] = str(pdf_path)
            st.session_state["pdf_bytes"] = pdf_path.read_bytes()

    if not st.session_state.get("agent_messages"):
        agent_lang = st.session_state.get("agent_lang", "de")
        st.session_state["agent_messages"] = [
            {
                "role": "assistant",
                "content": build_agent_summary(
                    quotation, matches,
                    applied_items=len(overrides), lang=agent_lang,
                ),
            }
        ] if quotation else []


# ---------- core flow ------------------------------------------------------
def pdf_output_path(content_hash: str, *, final: bool = False) -> Path:
    review_dir = st.session_state.get("review_dir")
    review_id = st.session_state.get("review_id") or content_hash

    if final:
        base = final_pdf_filename(review_id)
    else:
        base = draft_pdf_filename(review_id)

    if review_dir:
        path = Path(review_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path / base

    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / base

def rebuild_quotation_pdf(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    agent_lang: str,
    *,
    is_final: bool = False,
    show_status: bool = True,
):
    """Run pricing + render through the pipeline, applying manual overrides."""
    pipeline = get_pipeline()
    pdf_out = pdf_output_path(content_hash, final=is_final)
    work_dir = pdf_out.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    overrides = st.session_state.get("manual_discount_overrides", [])

    # Pull the per-review-effective company profile (saved settings +
    # any inline overrides the user typed in step 2). This is what
    # actually ends up baked into the PDF, replacing placeholder text
    # like [FIRMA] / [KONTAKTPERSON] / [LIEFERZEIT] with real values.
    company_profile = _resolve_company_profile()

    def _build(ctx: StepContext):
        base_quotation = pipeline.price(anfrage, matches, ctx)
        if overrides:
            built_quotation, built_applied_items = apply_manual_overrides(
                base_quotation, anfrage, overrides, lang=agent_lang,
            )
        else:
            built_quotation, built_applied_items = base_quotation, 0
        pipeline.render(
            anfrage, built_quotation, pdf_out, ctx,
            is_final=is_final,
            company_profile=company_profile,
        )
        return built_quotation, built_applied_items

    if show_status:
        label_prefix = "Final-PDF" if is_final else "Angebot"
        with st.status(
            f"{label_prefix} wird neu berechnet…", expanded=False,
        ) as status:
            progress = make_streamlit_progress(status)
            quotation, applied_items = _build(
                StepContext(work_dir=work_dir, progress=progress)
            )
            status.update(
                label=f"{label_prefix} aktualisiert",
                state="complete",
            )
    else:
        quotation, applied_items = _build(StepContext(work_dir=work_dir))

    if not is_final:
        # Draft state is what most of the UI binds to.
        st.session_state["quotation"] = quotation
        st.session_state["quotation_hash"] = content_hash
        st.session_state["generated_pdf_path"] = str(pdf_out)
        st.session_state["pdf_bytes"] = (
            pdf_out.read_bytes() if pdf_out.exists() else b""
        )

    _persist_review_outputs(
        anfrage=anfrage, matches=matches, quotation=quotation,
        overrides=overrides, pdf_out=pdf_out, is_final=is_final,
    )

    return quotation, applied_items, pdf_out


def maybe_auto_refresh(anfrage: Anfrage, matches, content_hash: str) -> None:
    """Auto-regenerate the PDF when the editor data has changed."""
    from quoting.api.settings_store import load_user_settings
    if not load_user_settings().workflow.auto_refresh_pdf:
        return

    current = _editor_state_hash(anfrage)
    last = st.session_state.get("editor_state_hash")
    if current == last:
        return

    changed_fields = st.session_state.get("changed_fields") or set()
    if last is None and not changed_fields:
        st.session_state["editor_state_hash"] = current
        return

    try:
        agent_lang = st.session_state.get("agent_lang", "de")
        rebuild_quotation_pdf(
            anfrage=anfrage, matches=matches,
            content_hash=content_hash, agent_lang=agent_lang,
            is_final=False,
            show_status=False,
        )
        st.session_state["editor_state_hash"] = current
    except Exception as exc:
        st.warning(
            f"Auto-Refresh fehlgeschlagen: {exc}",
        )


def render_generate_button(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    uploaded_name: str,
) -> None:
    is_review_mode = bool(st.session_state.get("review_dir"))

    button_label = (
        "Änderungen übernehmen & PDF aktualisieren"
        if is_review_mode
        else "Entwurf-Angebot erstellen"
    )

    if not st.button(
        button_label, type="primary", use_container_width=True,
    ):
        return

    pdf_out = None
    try:
        agent_lang = st.session_state.get("agent_lang", "de")
        quotation, applied_items, pdf_out = rebuild_quotation_pdf(
            anfrage=anfrage, matches=matches,
            content_hash=content_hash, agent_lang=agent_lang,
        )
        if pdf_out.exists():
            st.session_state["pdf_file_name"] = (
                f"ElringKlinger_Angebot_{safe_file_stub(uploaded_name)}_"
                f"{content_hash}.pdf"
            )
        st.session_state["agent_messages"] = [
            {
                "role": "assistant",
                "content": build_agent_summary(
                    quotation, matches,
                    applied_items=applied_items, lang=agent_lang,
                ),
            }
        ]
        st.session_state["editor_state_hash"] = _editor_state_hash(anfrage)
    except Exception as e:
        st.error(f"Fehler bei der Angebotserstellung: {e}")
        st.stop()

    if pdf_out and pdf_out.exists():
        if is_review_mode:
            st.success("Review aktualisiert. Das neue PDF wurde gespeichert.")
        else:
            st.success("Angebot erfolgreich erstellt.")
        st.download_button(
            label="PDF herunterladen",
            data=st.session_state.get("pdf_bytes", b""),
            file_name=st.session_state.get(
                "pdf_file_name",
                f"ElringKlinger_Angebot_{content_hash}.pdf",
            ),
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        st.error(
            "Fehler: PDF konnte nicht generiert werden. "
            "Prüfe, ob reportlab installiert ist."
        )


def finalize_pdf(anfrage: Anfrage, matches, content_hash: str) -> str:
    """Render the final PDF without AI warning and return its filename."""
    agent_lang = st.session_state.get("agent_lang", "de")
    _, _, pdf_out = rebuild_quotation_pdf(
        anfrage=anfrage,
        matches=matches,
        content_hash=content_hash,
        agent_lang=agent_lang,
        is_final=True,
    )
    return pdf_out.name


# ----------------------------------------------------------------- internal
def _editor_state_hash(anfrage: Anfrage) -> str:
    """Stable hash of all editor-visible Anfrage data."""
    payload = anfrage.model_dump(mode="json")
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    overrides = st.session_state.get("manual_discount_overrides") or []
    blob += json.dumps(overrides, sort_keys=True).encode("utf-8")
    company_overrides = st.session_state.get("company_profile_overrides") or {}
    blob += json.dumps(company_overrides, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _persist_review_outputs(
    anfrage: Anfrage, matches, quotation,
    overrides: list, pdf_out: Path,
    *,
    is_final: bool = False,
) -> None:
    """Mirror the final review-state to ``data/reviews/{review_id}``."""
    review_dir_raw = st.session_state.get("review_dir")
    review_id = st.session_state.get("review_id")

    if not review_dir_raw:
        return

    review_dir = Path(review_dir_raw)
    review_dir.mkdir(parents=True, exist_ok=True)

    if not is_final:
        write_json(review_dir / "anfrage_reviewed.json", anfrage)
        write_json(review_dir / "matches_reviewed.json", matches)
        write_json(review_dir / "quotation_reviewed.json", quotation)
        write_json(review_dir / "manual_overrides.json", overrides)
        write_json(
            review_dir / "review_state.json",
            {
                "review_id": review_id,
                "anfrage": anfrage,
                "matches": matches,
                "quotation": quotation,
                "manual_overrides": overrides,
                "pdf": str(pdf_out.name),
            },
        )

    if not review_id or not pdf_out.exists():
        return

    if not is_final:
        for stale_pdf in review_dir.glob("Angebot_Draft_*.pdf"):
            try:
                stale_pdf.unlink()
            except Exception:
                pass
        named_pdf = review_dir / draft_pdf_filename(review_id)
        if named_pdf.resolve() != pdf_out.resolve():
            shutil.copyfile(pdf_out, named_pdf)


def _load_saved_quotation(review_dir: Path) -> Quotation | None:
    candidates = [
        review_dir / "quotation_reviewed.json",
        review_dir / "03_quotation.json",
        review_dir / "pipeline" / "03_quotation.json",
    ]
    candidates.extend(sorted(review_dir.rglob("03_quotation.json")))
    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        data = read_json(path)
        if isinstance(data, dict):
            try:
                return _quotation_from_dict(data)
            except Exception:
                continue
    return None


def _quotation_from_dict(data: dict) -> Quotation:
    items = [
        QuotationItem(
            pos_nr=int(item.get("pos_nr", 0)),
            artikel_nr=str(item.get("artikel_nr", "")),
            bezeichnung=str(item.get("bezeichnung", "")),
            menge=float(item.get("menge", 0) or 0),
            einheit=str(item.get("einheit", "")),
            einzelpreis=float(item.get("einzelpreis", 0) or 0),
            rabatt_prozent=float(item.get("rabatt_prozent", 0) or 0),
            gesamtpreis=float(item.get("gesamtpreis", 0) or 0),
            bemerkung=str(item.get("bemerkung", "")),
        )
        for item in data.get("items", [])
        if isinstance(item, dict)
    ]
    return Quotation(
        kunde_firma=data.get("kunde_firma"),
        kunde_ansprechpartner=data.get("kunde_ansprechpartner"),
        kunde_email=data.get("kunde_email"),
        kundennummer=data.get("kundennummer"),
        belegnummer=data.get("belegnummer"),
        incoterms=data.get("incoterms"),
        zahlungsbedingungen=data.get("zahlungsbedingungen"),
        items=items,
        gesamtsumme=float(data.get("gesamtsumme", 0) or 0),
        waehrung=str(data.get("waehrung", "EUR")),
        warnungen=list(data.get("warnungen", [])),
    )
