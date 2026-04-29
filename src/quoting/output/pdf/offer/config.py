"""Static PDF configuration.

Prototype note:
All personal / company-specific production data is intentionally represented
as placeholders. Replace these values later with real ERP / CRM data.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class OfferPdfConfig:
    # Brand / sender placeholders
    company_name: str = "[FIRMA]"
    company_address_html: str = "[STRASSE]<br/>[PLZ ORT]<br/>[LAND]"

    # Contact placeholders
    contact_person: str = "[KONTAKTPERSON]"
    contact_phone: str = "[TELEFON]"
    contact_email: str = "[E-MAIL]"

    # Header placeholders
    document_no_fallback: str = "ENTWURF"
    customer_no_fallback: str = "[KUNDEN-NR.]"

    # Commercial prototype defaults
    delivery_term: str = "[LIEFERBEDINGUNG]"
    payment_term: str = "[ZAHLUNGSBEDINGUNG]"
    delivery_time: str = "[LIEFERZEIT]"
    delivery_plant: str = "[LIEFERWERK]"
    validity_days: int = 28

    # Logo path relative to src/quoting/
    logo_relative_path: Path = Path("ui/assets/logo_elringklinger.png")

    # Approval-aware rendering. When ``is_final`` is True, the red AI
    # warning banner is suppressed so the PDF can be sent to customers.
    is_final: bool = False

    # Prototype texts
    ai_notice: str = (
        "AI GENERATED DRAFT: Dieser Angebotsentwurf wurde automatisch erstellt "
        "und muss vor Versand fachlich und kaufmännisch geprüft werden."
    )
    intro_lines: tuple[str, ...] = (
        "Vielen Dank für Ihre Anfrage. Wir bieten Ihnen nachfolgend unverbindlich an:",
    )
    closing_lines: tuple[str, ...] = (
        "Mit freundlichen Grüßen",
    )
    closing_lines_draft: tuple[str, ...] = (
        "Dies ist ein Prototyp-Angebot und dient ausschließlich der internen Prüfung.",
        "Mit freundlichen Grüßen",
        "[NAME / SIGNATUR]",
    )

    footer_left: tuple[str, ...] = (
        "[GESCHÄFTSFÜHRUNG]",
        "[SITZ DER GESELLSCHAFT]",
        "[REGISTER / UST-ID]",
    )
    footer_bank: tuple[str, ...] = (
        "[BANKVERBINDUNG]",
        "[BANK 1]",
        "[BANK 2]",
    )
    footer_iban: tuple[str, ...] = (
        "IBAN",
        "[IBAN 1]",
        "[IBAN 2]",
    )
    footer_bic: tuple[str, ...] = (
        "BIC",
        "[BIC 1]",
        "[BIC 2]",
    )

    def with_overrides(self, **kwargs) -> "OfferPdfConfig":
        """Return a copy with selected fields overridden."""
        return replace(self, **kwargs)

    def effective_closing(self) -> tuple[str, ...]:
        """Closing block uses the same contact person as the offer header."""
        lines = self.closing_lines if self.is_final else self.closing_lines_draft
        signature_name = (self.contact_person or "").strip() or "[KONTAKTPERSON]"
        resolved = tuple(
            signature_name if line == "[NAME / SIGNATUR]" else line
            for line in lines
        )
        if signature_name not in resolved:
            resolved += (signature_name,)
        return resolved


def config_from_company_profile(profile, *, is_final: bool = False) -> OfferPdfConfig:
    """Build a config from a CompanyProfile dataclass (settings_store)."""
    if profile is None:
        return OfferPdfConfig(is_final=is_final)

    addr_html_parts = [
        profile.company_address,
        profile.company_zip_city,
        profile.company_country,
    ]
    addr_html = "<br/>".join(p for p in addr_html_parts if p) or "[ADRESSE]"

    return OfferPdfConfig(
        company_name=profile.company_name or "[FIRMA]",
        company_address_html=addr_html,
        contact_person=profile.contact_person or "[KONTAKTPERSON]",
        contact_phone=profile.contact_phone or "[TELEFON]",
        contact_email=profile.contact_email or "[E-MAIL]",
        delivery_term=profile.delivery_term or "[LIEFERBEDINGUNG]",
        payment_term=profile.payment_term or "[ZAHLUNGSBEDINGUNG]",
        validity_days=int(profile.validity_days or 28),
        is_final=is_final,
    )
