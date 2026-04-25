"""Pydantic schema for extracted RFQ data."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]


class Position(BaseModel):
    """One line item from an RFQ."""

    pos_nr: int
    artikelnummer: str
    bezeichnung: str = ""
    menge: float
    einheit: str
    liefertermin: str | None = None
    werkstoff: str | None = None
    werkstoff_alternativen: list[str] = Field(default_factory=list)
    zeichnungsnummer: str | None = None
    abmessungen: str | None = None
    gewicht_stueck_kg: float | None = None
    ist_zertifikat: bool = False
    confidence: Confidence
    source_quote: str

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


class Anfrage(BaseModel):
    """Complete parsed RFQ."""

    vorgangsnummer: str | None = None
    belegnummer: str | None = None
    datum: str | None = None
    kunde_firma: str | None = None
    kunde_ansprechpartner: str | None = None
    kunde_email: str | None = None
    incoterms: str | None = None
    zahlungsbedingungen: str | None = None
    positionen: list[Position]
    unsicherheiten: list[str] = Field(default_factory=list)