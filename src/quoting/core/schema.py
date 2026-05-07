"""Pydantic schema for extracted RFQ data."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]


class Evidence(BaseModel):
    """Source reference for a single extracted value."""

    source_file: str | None = None
    source_page: int | None = None
    source_row: int | None = None
    source_quote: str | None = None


class Position(BaseModel):
    """One line item from an RFQ."""

    pos_nr: int
    artikelnummer: str
    bezeichnung: str = ""
    menge: float
    einheit: str
    liefertermin: str | None = None
    lieferzeit: str | None = None
    lieferwerk: str | None = None
    werkstoff: str | None = None
    werkstoff_alternativen: list[str] = Field(default_factory=list)
    zeichnungsnummer: str | None = None
    abmessungen: str | None = None
    gewicht_stueck_kg: float | None = None
    ist_zertifikat: bool = False
    confidence: Confidence
    source_quote: str
    source_file: str | None = None
    source_page: int | None = None
    source_row: int | None = None

    @field_validator("artikelnummer", mode="before")
    @classmethod
    def _normalize_artikelnummer(cls, v: str | None) -> str:
        if v is None:
            return ""
        return " ".join(str(v).split())

    @field_validator("bezeichnung", mode="before")
    @classmethod
    def _normalize_bezeichnung(cls, v: str | None) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("menge", mode="before")
    @classmethod
    def _coerce_menge(cls, v) -> float:
        if isinstance(v, str):
            v = v.replace(",", ".").strip()
        return float(v)

    @field_validator("einheit", mode="before")
    @classmethod
    def _default_einheit(cls, v) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "Stk"
        return str(v).strip()


class Anfrage(BaseModel):
    """Complete parsed RFQ."""

    vorgangsnummer: str | None = None
    belegnummer: str | None = None
    datum: str | None = None
    kunde_firma: str | None = None
    kunde_ansprechpartner: str | None = None
    kunde_email: str | None = None
    kundennummer: str | None = None
    incoterms: str | None = None
    zahlungsbedingungen: str | None = None
    positionen: list[Position]
    unsicherheiten: list[str] = Field(default_factory=list)
    header_evidence: dict[str, Evidence] = Field(default_factory=dict)
