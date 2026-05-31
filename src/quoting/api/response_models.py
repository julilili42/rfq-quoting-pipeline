"""Pydantic response models for the frontend-facing API.

These mirror the structures historically returned as raw ``dict`` from the
routers. Declaring them as ``response_model`` makes ``/openapi.json``
self-describing so the React UI can generate types from it instead of
hand-mirroring schemas in ``review-ui/src/shared/schemas/``.

Several pipeline data classes (``MatchResult``, ``Quotation``,
``QuotationItem``) live as ``@dataclass`` further down the stack. We
mirror them here rather than converting them — keeps the pipeline layer
untouched and gives the API layer a single owner for its wire shapes.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quoting.core import Anfrage

MatchStatus = Literal["exact", "fuzzy", "semantic", "no_match"]
ReviewStatus = Literal["abgeschlossen", "pdf_bereit", "in_arbeit"]
ApprovalState = Literal["draft_generated", "reviewed", "approved", "ready_to_send"]
PipelineStatus = Literal["running", "completed", "failed"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class MailAttachmentMeta(BaseModel):
    """One attachment as stored alongside a review's mail payload."""

    model_config = ConfigDict(extra="allow")

    name: str
    contentType: str | None = None
    size: int | None = None
    id: str | None = None


class MailMeta(BaseModel):
    """Mail header + body + attachments as the UI consumes them."""

    model_config = ConfigDict(populate_by_name=True)

    subject: str = ""
    from_: str = Field(default="", alias="from")
    body: str = ""
    attachments: list[MailAttachmentMeta] = Field(default_factory=list)


class OutgoingMailAttachment(BaseModel):
    """Additional file the user wants on the outgoing quotation email."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    contentType: str | None = None
    size: int | None = None
    url: str


class MatchResultModel(BaseModel):
    """Mirror of ``quoting.matching.matcher.MatchResult.to_dict``."""

    pos_nr: int
    status: MatchStatus
    score: float
    matched_artikelnr: str | None = None
    matched_bezeichnung: str | None = None
    matched_row: dict[str, Any] | None = None
    manual: bool = False


class QuotationItemModel(BaseModel):
    """Mirror of ``quoting.pricing.quotation.QuotationItem``."""

    pos_nr: int
    artikel_nr: str
    bezeichnung: str
    menge: float
    einheit: str
    einzelpreis: float
    rabatt_prozent: float = 0.0
    gesamtpreis: float
    bemerkung: str = ""
    basispreis_eur: float = 0.0
    margin_eur: float = 0.0
    margin_pct: float = 0.0


class QuotationModel(BaseModel):
    """Mirror of ``quoting.pricing.quotation.Quotation.to_dict``."""

    kunde_firma: str | None = None
    kunde_ansprechpartner: str | None = None
    kunde_email: str | None = None
    kundennummer: str | None = None
    belegnummer: str | None = None
    incoterms: str | None = None
    zahlungsbedingungen: str | None = None
    items: list[QuotationItemModel]
    gesamtsumme: float
    waehrung: str
    warnungen: list[str]


# Manual overrides are persisted and forwarded as opaque dicts; the frontend
# owns the discriminated-union shape (see review-ui/src/shared/schemas/quotation.ts).
# Typing this as dict[str, Any] keeps the wire compatible while the UI
# remains the source of truth for the variants.
ManualOverridePayload = dict[str, Any]


class ReviewListItem(BaseModel):
    """One row in ``GET /api/reviews``."""

    review_id: str
    created_at: str
    updated_at: str
    subject: str
    sender: str
    customer: str = ""
    positions: int
    confidence_high: int
    confidence_medium: int
    confidence_low: int
    matches_exact: int
    matches_fuzzy: int
    matches_semantic: int
    matches_no_match: int
    total_eur: float
    currency: str
    status: ReviewStatus
    has_pdf: bool
    manual_overrides_count: int
    escalation: dict[str, Any] | None = None
    extracted_articles: list[str] = Field(default_factory=list)


class ReviewDetail(BaseModel):
    """Full payload returned by ``GET /api/reviews/{id}``."""

    review_id: str
    created_at: str | None = None
    anfrage: Anfrage
    original_anfrage: Anfrage
    matches: list[MatchResultModel] = Field(default_factory=list)
    quotation: QuotationModel | None = None
    manual_overrides: list[ManualOverridePayload] = Field(default_factory=list)
    mail: MailMeta
    has_draft_pdf: bool
    has_final_pdf: bool
    mail_attachments: list[OutgoingMailAttachment] = Field(default_factory=list)
    requirements_acknowledged: list[int] = Field(default_factory=list)
    escalation: dict[str, Any] | None = None


class FinalizeResponse(BaseModel):
    final_pdf_path: str


class ReplyBodyResponse(BaseModel):
    """LLM-generated cover-letter body for the Outlook reply."""

    body: str
    language: Literal["de", "en"]
    model: str
