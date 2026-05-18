"""Resolve extraction evidence to highlight areas in original PDFs."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import fitz

log = logging.getLogger(__name__)

HighlightStatus = Literal["exact", "candidate", "block", "fuzzy", "page_only", "not_found"]
TargetKind = Literal["position", "header", "generic"]

# Tuning constants — change here, not in the functions below.
_MAX_EXACT_QUOTE_LEN    = 180   # quotes longer than this are too noisy for exact search
_MIN_FUZZY_NEEDLE_LEN   = 8     # very short strings produce too many false positives
_FUZZY_SCORE_THRESHOLD  = 78    # minimum rapidfuzz partial_ratio to accept a block match
_MAX_MATCHED_TEXT_LEN   = 160   # truncate matched_text stored in HighlightResult
_MIN_CANDIDATE_LEN      = 4     # shorter tokens are low-information
_MAX_CANDIDATE_LEN      = 120   # guards against accidentally passing full sentences
_LOW_INFO_MAX_LABEL_LEN = 4     # single short alpha labels (e.g. "pos") are noise
_BLOCK_HIT_TOLERANCE_PX = 2     # pixel tolerance when testing quad centre vs block bbox
_CANDIDATE_RECT_PADDING = 1.5   # padding added to candidate highlight rect
_BLOCK_RECT_PADDING     = 2.0   # padding added to containing-block highlight rect


@dataclass(frozen=True)
class HighlightArea:
    """A highlight rectangle in React PDF Viewer percentage coordinates."""

    pageIndex: int
    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class HighlightResult:
    status: HighlightStatus
    areas: list[HighlightArea]
    pageIndex: int | None = None
    matched_text: str | None = None
    message: str | None = None


_EMAIL_RE = re.compile(r"(?iu)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
_TOKEN_RE = re.compile(r"(?u)[A-ZÄÖÜ0-9][A-ZÄÖÜa-zäöüß0-9./:_-]{3,}")
_SPACE_RE = re.compile(r"\s+")
_LOW_INFORMATION_CANDIDATES = {
    "artikel",
    "artikelnr",
    "artikelnummer",
    "date",
    "datum",
    "email",
    "e-mail",
    "einheit",
    "fax",
    "firma",
    "kunde",
    "mail",
    "menge",
    "name",
    "phone",
    "pos",
    "position",
    "seite",
    "tel",
    "telefon",
}


def resolve_pdf_highlight(
    pdf_path: Path,
    *,
    source_page: int | None = None,
    source_quote: str | None = None,
    candidates: list[str] | None = None,
    target_kind: TargetKind = "generic",
) -> HighlightResult:
    """Resolve a source reference to page-relative highlight areas.

    The LLM-provided ``source_quote`` is useful context, but it is not a
    reliable exact search string for PDFs: line breaks, OCR differences and
    paraphrases are common. We therefore prefer deterministic candidates
    supplied by the UI, such as article numbers or header field values.
    """
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        return HighlightResult("not_found", [], message=f"PDF could not be opened: {exc}")

    with doc:
        if doc.page_count == 0:
            return HighlightResult("not_found", [], message="PDF contains no pages")

        preferred_pages = _page_indices(doc.page_count, source_page)
        fallback_pages = [i for i in range(doc.page_count) if i not in preferred_pages]
        pages = preferred_pages + fallback_pages

        quote = _clean(source_quote)
        if quote:
            exact = _search_exact(doc, preferred_pages, quote)
            if exact.areas:
                return exact

        candidate_values = _candidate_values(candidates or [], quote)
        candidate = _search_candidates(doc, pages, candidate_values, target_kind)
        if candidate.areas:
            return candidate

        if quote:
            fuzzy = _search_fuzzy_blocks(doc, pages, quote)
            if fuzzy.areas:
                return fuzzy

        page_only_index = _resolve_page_index(doc.page_count, source_page)
        if page_only_index is not None:
            return HighlightResult("page_only", [], pageIndex=page_only_index)

    return HighlightResult("not_found", [], message="No matching PDF text found")


def _resolve_page_index(page_count: int, source_page: int | None) -> int | None:
    """Return 0-based page index, or None if source_page is absent/out-of-range."""
    if source_page is None:
        return None
    idx = source_page - 1
    return idx if 0 <= idx < page_count else None


def _page_indices(page_count: int, source_page: int | None) -> list[int]:
    idx = _resolve_page_index(page_count, source_page)
    return [idx] if idx is not None else list(range(page_count))


def _search_exact(doc: fitz.Document, page_indices: list[int], quote: str) -> HighlightResult:
    if len(quote) > _MAX_EXACT_QUOTE_LEN:
        return HighlightResult("not_found", [])

    for page_index in page_indices:
        page = doc[page_index]
        quads = page.search_for(quote, quads=True)
        if quads:
            return HighlightResult(
                "exact",
                [_area_from_rect(page, quad.rect, page_index) for quad in quads],
                pageIndex=page_index,
                matched_text=quote,
            )
    return HighlightResult("not_found", [])


def _search_candidates(
    doc: fitz.Document,
    page_indices: list[int],
    candidates: list[str],
    target_kind: TargetKind,
) -> HighlightResult:
    for candidate in candidates:
        for page_index in page_indices:
            page = doc[page_index]
            quads = page.search_for(candidate, quads=True)
            if not quads:
                continue

            if target_kind == "position":
                block_rect = _containing_block_rect(page, quads[0].rect)
                if block_rect is not None:
                    return HighlightResult(
                        "block",
                        [_area_from_rect(page, block_rect, page_index)],
                        pageIndex=page_index,
                        matched_text=candidate,
                    )

            return HighlightResult(
                "candidate",
                [_area_from_rect(page, quad.rect, page_index) for quad in quads],
                pageIndex=page_index,
                matched_text=candidate,
            )
    return HighlightResult("not_found", [])


def _search_fuzzy_blocks(doc: fitz.Document, page_indices: list[int], quote: str) -> HighlightResult:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        log.debug("rapidfuzz not installed; fuzzy block search skipped")
        return HighlightResult("not_found", [])

    needle = _normalise_for_match(quote)
    if len(needle) < _MIN_FUZZY_NEEDLE_LEN:
        return HighlightResult("not_found", [])

    best: tuple[float, int, Any, str] | None = None
    for page_index in page_indices:
        page = doc[page_index]
        for block in _text_blocks(page):
            text = str(block[4])
            score = float(fuzz.partial_ratio(needle, _normalise_for_match(text)))
            if best is None or score > best[0]:
                best = (score, page_index, block, text)

    if best is None or best[0] < _FUZZY_SCORE_THRESHOLD:
        return HighlightResult("not_found", [])

    score, page_index, block, text = best
    page = doc[page_index]
    rect = _rect_from_tuple(page, block[:4], padding=_CANDIDATE_RECT_PADDING)
    return HighlightResult(
        "fuzzy",
        [_area_from_rect(page, rect, page_index)],
        pageIndex=page_index,
        matched_text=text[:_MAX_MATCHED_TEXT_LEN],
        message=f"Fuzzy score {score:.0f}",
    )


def _candidate_values(candidates: list[str], quote: str | None) -> list[str]:
    values: list[str] = []

    if quote:
        values.extend(_EMAIL_RE.findall(quote))

    values.extend(candidates)

    if quote:
        values.extend(_TOKEN_RE.findall(quote))

    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if not cleaned or len(cleaned) < _MIN_CANDIDATE_LEN or len(cleaned) > _MAX_CANDIDATE_LEN:
            continue
        if _is_low_information_candidate(cleaned):
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _is_low_information_candidate(value: str) -> bool:
    label = value.casefold().strip(" .:-")
    if label in _LOW_INFORMATION_CANDIDATES:
        return True
    return label.isalpha() and len(label) <= _LOW_INFO_MAX_LABEL_LEN


def _containing_block_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect | None:
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    best = None
    best_area = None
    for block in _text_blocks(page):
        x0, y0, x1, y1 = block[:4]
        t = _BLOCK_HIT_TOLERANCE_PX
        if x0 - t <= cx <= x1 + t and y0 - t <= cy <= y1 + t:
            area = (x1 - x0) * (y1 - y0)
            if best is None or area < best_area:
                best = block
                best_area = area
    if best is None:
        return None
    return _rect_from_tuple(page, best[:4], padding=_BLOCK_RECT_PADDING)


def _text_blocks(page: fitz.Page) -> list:
    return [block for block in page.get_text("blocks", sort=True) if len(block) >= 7 and block[6] == 0]


def _rect_from_tuple(page: fitz.Page, coords: tuple, *, padding: float) -> fitz.Rect:
    import fitz

    rect = fitz.Rect(*coords)
    rect.x0 = max(page.rect.x0, rect.x0 - padding)
    rect.y0 = max(page.rect.y0, rect.y0 - padding)
    rect.x1 = min(page.rect.x1, rect.x1 + padding)
    rect.y1 = min(page.rect.y1, rect.y1 + padding)
    return rect


def _area_from_rect(page: fitz.Page, rect: fitz.Rect, page_index: int) -> HighlightArea:
    page_rect = page.rect
    width = page_rect.width or 1
    height = page_rect.height or 1
    return HighlightArea(
        pageIndex=page_index,
        left=round(((rect.x0 - page_rect.x0) / width) * 100, 4),
        top=round(((rect.y0 - page_rect.y0) / height) * 100, 4),
        width=round((rect.width / width) * 100, 4),
        height=round((rect.height / height) * 100, 4),
    )


def _clean(value: str | None) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _normalise_for_match(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip().casefold()
