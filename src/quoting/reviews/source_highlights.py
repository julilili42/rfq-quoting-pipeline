"""Resolve extraction evidence to highlight areas in original PDFs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HighlightStatus = Literal["exact", "candidate", "block", "fuzzy", "page_only", "not_found"]
TargetKind = Literal["position", "header", "generic"]


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

        page_only_index = _page_index_for_page_only(doc.page_count, source_page)
        if page_only_index is not None:
            return HighlightResult("page_only", [], pageIndex=page_only_index)

    return HighlightResult("not_found", [], message="No matching PDF text found")


def _page_indices(page_count: int, source_page: int | None) -> list[int]:
    if source_page is None:
        return list(range(page_count))
    page_index = source_page - 1
    if page_index < 0 or page_index >= page_count:
        return list(range(page_count))
    return [page_index]


def _page_index_for_page_only(page_count: int, source_page: int | None) -> int | None:
    if source_page is None:
        return None
    page_index = source_page - 1
    if page_index < 0 or page_index >= page_count:
        return None
    return page_index


def _search_exact(doc, page_indices: list[int], quote: str) -> HighlightResult:
    if len(quote) > 180:
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
    doc,
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


def _search_fuzzy_blocks(doc, page_indices: list[int], quote: str) -> HighlightResult:
    try:
        from rapidfuzz import fuzz
    except Exception:
        return HighlightResult("not_found", [])

    needle = _normalise_for_match(quote)
    if len(needle) < 8:
        return HighlightResult("not_found", [])

    best: tuple[float, int, object, str] | None = None
    for page_index in page_indices:
        page = doc[page_index]
        for block in _text_blocks(page):
            text = str(block[4])
            score = float(fuzz.partial_ratio(needle, _normalise_for_match(text)))
            if best is None or score > best[0]:
                best = (score, page_index, block, text)

    if best is None or best[0] < 78:
        return HighlightResult("not_found", [])

    score, page_index, block, text = best
    page = doc[page_index]
    rect = _rect_from_tuple(page, block[:4], padding=1.5)
    return HighlightResult(
        "fuzzy",
        [_area_from_rect(page, rect, page_index)],
        pageIndex=page_index,
        matched_text=text[:160],
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
        if not cleaned or len(cleaned) < 4 or len(cleaned) > 120:
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
    return label.isalpha() and len(label) <= 4


def _containing_block_rect(page, rect):
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    best = None
    best_area = None
    for block in _text_blocks(page):
        x0, y0, x1, y1 = block[:4]
        if x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2:
            area = (x1 - x0) * (y1 - y0)
            if best is None or area < best_area:
                best = block
                best_area = area
    if best is None:
        return None
    return _rect_from_tuple(page, best[:4], padding=2.0)


def _text_blocks(page):
    return [block for block in page.get_text("blocks", sort=True) if len(block) >= 7 and block[6] == 0]


def _rect_from_tuple(page, coords, *, padding: float):
    import fitz

    rect = fitz.Rect(*coords)
    rect.x0 = max(page.rect.x0, rect.x0 - padding)
    rect.y0 = max(page.rect.y0, rect.y0 - padding)
    rect.x1 = min(page.rect.x1, rect.x1 + padding)
    rect.y1 = min(page.rect.y1, rect.y1 + padding)
    return rect


def _area_from_rect(page, rect, page_index: int) -> HighlightArea:
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
