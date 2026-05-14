"""Own-company context for RFQ extraction.

The extractor must distinguish the quote sender (us) from the RFQ customer.
This module makes that context explicit in the LLM prompt and defensively
removes own-company values if they still come back as customer fields.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..core import Anfrage


@dataclass(frozen=True)
class OwnPartyContext:
    company_name: str | None = None
    company_address: str | None = None
    company_zip_city: str | None = None
    company_country: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    company_aliases: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_profile(cls, profile: Any | None) -> OwnPartyContext:
        if profile is None:
            return cls()

        company_name = _clean(getattr(profile, "company_name", None))
        aliases: list[str] = []
        if company_name and "elringklinger" in _normalize_identity(company_name):
            aliases.extend(["ElringKlinger AG", "Elring Klinger", "ElringKlinger"])

        return cls(
            company_name=company_name,
            company_address=_clean(getattr(profile, "company_address", None)),
            company_zip_city=_clean(getattr(profile, "company_zip_city", None)),
            company_country=_clean(getattr(profile, "company_country", None)),
            contact_person=_clean(getattr(profile, "contact_person", None)),
            contact_phone=_clean(getattr(profile, "contact_phone", None)),
            contact_email=_clean(getattr(profile, "contact_email", None)),
            company_aliases=tuple(dict.fromkeys(aliases)),
        )

    def has_values(self) -> bool:
        return any([
            self.company_name,
            self.company_address,
            self.company_zip_city,
            self.company_country,
            self.contact_person,
            self.contact_phone,
            self.contact_email,
            self.company_aliases,
        ])


def load_own_party_context() -> OwnPartyContext:
    """Load sender-side company/contact data from persisted UI settings."""
    try:
        from quoting.api.settings_store import load_user_settings

        return OwnPartyContext.from_profile(load_user_settings().company)
    except Exception:
        return OwnPartyContext()


def format_own_party_prompt_context(ctx: OwnPartyContext | None) -> str:
    """Return a prompt section telling the LLM what not to extract as customer."""
    if ctx is None or not ctx.has_values():
        return ""

    lines = [
        "The quoting tool is used by the quote sender. The following values",
        "belong to OUR company/contact, not to the RFQ customer:",
    ]
    if ctx.company_name:
        lines.append(f"- own company: {ctx.company_name}")
    if ctx.company_aliases:
        lines.append(f"- own company aliases: {', '.join(ctx.company_aliases)}")
    if ctx.company_address:
        lines.append(f"- own address: {ctx.company_address}")
    if ctx.company_zip_city:
        lines.append(f"- own zip/city: {ctx.company_zip_city}")
    if ctx.company_country:
        lines.append(f"- own country: {ctx.company_country}")
    if ctx.contact_person:
        lines.append(f"- own contact person: {ctx.contact_person}")
    if ctx.contact_email:
        lines.append(f"- own contact email: {ctx.contact_email}")
    if ctx.contact_phone:
        lines.append(f"- own contact phone: {ctx.contact_phone}")

    lines.extend([
        "",
        "Never use these own values for kunde_firma, kunde_ansprechpartner,",
        "kunde_email or kundennummer when they appear as recipient, signature,",
        "footer, logo, sender address block, quotation template, or internal",
        "ElringKlinger contact.",
        "Extract customer fields only from the requester, buyer, sender, or",
        "customer letterhead. If only own company/contact data is visible for a",
        "customer field, leave that field null and add an uncertainty.",
    ])
    return "\n".join(lines)


def sanitize_own_customer_fields(
    anfrage: Anfrage,
    ctx: OwnPartyContext | None,
) -> list[str]:
    """Clear customer header fields that match our own company/contact data."""
    if ctx is None:
        return []

    cleared: list[str] = []
    if _looks_like_own_company(anfrage.kunde_firma, ctx):
        anfrage.kunde_firma = None
        cleared.append("kunde_firma")
    if _looks_like_own_contact(anfrage.kunde_ansprechpartner, ctx):
        anfrage.kunde_ansprechpartner = None
        cleared.append("kunde_ansprechpartner")
    if _looks_like_own_email(anfrage.kunde_email, ctx):
        anfrage.kunde_email = None
        cleared.append("kunde_email")

    if not cleared:
        return []

    for field_name in cleared:
        anfrage.header_evidence.pop(field_name, None)

    msg = (
        "Eigene Firmen-/Kontaktdaten wurden nicht als Kundendaten uebernommen: "
        + ", ".join(cleared)
    )
    if msg not in anfrage.unsicherheiten:
        anfrage.unsicherheiten.append(msg)
    return cleared


def _looks_like_own_company(value: str | None, ctx: OwnPartyContext) -> bool:
    candidate = _normalize_identity(value)
    if not candidate:
        return False

    aliases = [ctx.company_name, *ctx.company_aliases, "ElringKlinger", "Elring Klinger"]
    for alias in aliases:
        norm_alias = _normalize_identity(alias)
        if len(norm_alias) < 6:
            continue
        if candidate == norm_alias or norm_alias in candidate:
            return True
    return False


def _looks_like_own_contact(value: str | None, ctx: OwnPartyContext) -> bool:
    candidate = _normalize_identity(value)
    contact = _normalize_identity(ctx.contact_person)
    if not candidate or len(contact) < 6:
        return False
    return candidate == contact or contact in candidate


def _looks_like_own_email(value: str | None, ctx: OwnPartyContext) -> bool:
    if not value or not ctx.contact_email:
        return False
    return ctx.contact_email.strip().lower() in value.strip().lower()


def _normalize_identity(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
