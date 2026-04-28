"""Per-review quotation flow — pricing, rendering, persistence.

Sits on top of the pipeline's per-step API. The only thing that's *not*
a pipeline step is the manual-override layer between pricing and
rendering, because it's a UI-specific concept (the chat agent's
human-in-the-loop edits).
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from quoting.core import Anfrage
from quoting.pipeline import StepContext
from quoting.pricing import Quotation, QuotationItem
from quoting.ui.review_agent import apply_manual_overrides, build_agent_summary
from quoting.ui.review_ui.resources import get_pipeline, make_streamlit_progress
from quoting.ui.review_ui.state import safe_file_stub


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
    overrides = _load_json(review_dir / "manual_overrides.json")
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

        pdf_path = _find_current_pdf(review_dir, review_id)
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
            ]


# ---------- core flow ------------------------------------------------------

def pdf_output_path(content_hash: str) -> Path:
    review_dir = st.session_state.get("review_dir")
    if review_dir:
        path = Path(review_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path / "draft_angebot.pdf"
    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / "draft_angebot.pdf"


def rebuild_quotation_pdf(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    agent_lang: str,
):
    """Run pricing + render through the pipeline, applying manual overrides.

    Live progress is reported into a ``st.status`` block so the user sees
    each step happen instead of staring at a generic spinner.
    """
    pipeline = get_pipeline()
    pdf_out = pdf_output_path(content_hash)
    work_dir = pdf_out.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    overrides = st.session_state.get("manual_discount_overrides", [])

    with st.status(
        "Angebot wird neu berechnet…", expanded=False,
    ) as status:
        progress = make_streamlit_progress(status)
        ctx = StepContext(work_dir=work_dir, progress=progress)

        base_quotation = pipeline.price(anfrage, matches, ctx)

        if overrides:
            quotation, applied_items = apply_manual_overrides(
                base_quotation, anfrage, overrides, lang=agent_lang,
            )
        else:
            quotation, applied_items = base_quotation, 0

        pipeline.render(anfrage, quotation, pdf_out, ctx)

        status.update(
            label=(
                f"✓ Angebot fertig — "
                f"{quotation.gesamtsumme:.2f} {quotation.waehrung}"
            ),
            state="complete",
        )

    st.session_state["quotation"] = quotation
    st.session_state["quotation_hash"] = content_hash
    st.session_state["generated_pdf_path"] = str(pdf_out)
    st.session_state["pdf_bytes"] = (
        pdf_out.read_bytes() if pdf_out.exists() else b""
    )

    _persist_review_outputs(
        anfrage=anfrage, matches=matches, quotation=quotation,
        overrides=overrides, pdf_out=pdf_out,
    )
    return quotation, applied_items, pdf_out


def render_generate_button(
    anfrage: Anfrage,
    matches,
    content_hash: str,
    uploaded_name: str,
) -> None:
    is_review_mode = bool(st.session_state.get("review_dir"))
    button_label = (
        "💾 Änderungen übernehmen & PDF aktualisieren"
        if is_review_mode
        else "📝 Entwurf-Angebot erstellen"
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
    except Exception as e:
        st.error(f"Fehler bei der Angebotserstellung: {e}")
        st.stop()

    if pdf_out and pdf_out.exists():
        if is_review_mode:
            st.success("✅ Review aktualisiert. Das neue PDF wurde gespeichert.")
        else:
            st.success("✅ Angebot erfolgreich erstellt!")

        st.download_button(
            label="📥 PDF herunterladen",
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


# ----------------------------------------------------------------- internal

def _persist_review_outputs(
    anfrage: Anfrage, matches, quotation,
    overrides: list, pdf_out: Path,
) -> None:
    """Mirror the final review-state to ``data/reviews/{review_id}``."""
    review_dir_raw = st.session_state.get("review_dir")
    review_id = st.session_state.get("review_id")
    if not review_dir_raw:
        return

    review_dir = Path(review_dir_raw)
    review_dir.mkdir(parents=True, exist_ok=True)

    _write_json(review_dir / "anfrage_reviewed.json", anfrage)
    _write_json(review_dir / "matches_reviewed.json", matches)
    _write_json(review_dir / "quotation_reviewed.json", quotation)
    _write_json(review_dir / "manual_overrides.json", overrides)
    _write_json(
        review_dir / "review_state.json",
        {
            "review_id": review_id,
            "anfrage": _to_jsonable(anfrage),
            "matches": _to_jsonable(matches),
            "quotation": _to_jsonable(quotation),
            "manual_overrides": _to_jsonable(overrides),
            "pdf": str(pdf_out.name),
        },
    )

    if not review_id or not pdf_out.exists():
        return

    for stale_pdf in review_dir.glob("Angebot_Draft_*.pdf"):
        try:
            stale_pdf.unlink()
        except Exception:
            pass

    named_pdf = review_dir / f"Angebot_Draft_{review_id}.pdf"
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
        data = _load_json(path)
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
        belegnummer=data.get("belegnummer"),
        incoterms=data.get("incoterms"),
        zahlungsbedingungen=data.get("zahlungsbedingungen"),
        items=items,
        gesamtsumme=float(data.get("gesamtsumme", 0) or 0),
        waehrung=str(data.get("waehrung", "EUR")),
        warnungen=list(data.get("warnungen", [])),
    )


def _find_current_pdf(review_dir: Path, review_id: str | None) -> Path | None:
    candidates: list[Path] = []
    if review_id:
        candidates.append(review_dir / f"Angebot_Draft_{review_id}.pdf")
    candidates.append(review_dir / "draft_angebot.pdf")
    candidates.extend(sorted(review_dir.rglob("*_ANGEBOT_DRAFT.pdf")))
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_to_jsonable(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _to_jsonable(value: Any):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value
