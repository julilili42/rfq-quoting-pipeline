from __future__ import annotations

from quoting.core import Anfrage
from quoting.core.schema import Evidence
from quoting.extraction.own_party import (
    OwnPartyContext,
    format_own_party_prompt_context,
    sanitize_own_customer_fields,
)
from quoting.extraction.prompts import build_prompt


def test_own_party_prompt_context_warns_against_customer_extraction():
    ctx = OwnPartyContext(
        company_name="ElringKlinger",
        contact_person="Julian Jurcevic",
        contact_email="julian@example.com",
        company_aliases=("ElringKlinger AG",),
    )

    section = format_own_party_prompt_context(ctx)

    assert "own company: ElringKlinger" in section
    assert "own company aliases: ElringKlinger AG" in section
    assert "own contact person: Julian Jurcevic" in section
    assert "Never use these own values for kunde_firma" in section


def test_build_prompt_puts_own_company_context_before_mail_body():
    prompt = build_prompt(
        "{}",
        "Bitte Angebot",
        ["=== PDF: Anfrage.pdf ==="],
        "own company: ElringKlinger",
        "emails: kunde@example.com",
    )

    assert "=== OUR COMPANY / DO NOT EXTRACT AS CUSTOMER ===" in prompt
    assert "=== LOCAL CANDIDATE HINTS ===" in prompt
    assert prompt.index("own company: ElringKlinger") < prompt.index("=== MAIL BODY ===")
    assert prompt.index("=== LOCAL CANDIDATE HINTS ===") < prompt.index("=== MAIL BODY ===")
    assert prompt.index("=== MAIL BODY ===") < prompt.index("=== PDF: Anfrage.pdf ===")


def test_sanitize_clears_own_values_from_customer_fields():
    ctx = OwnPartyContext(
        company_name="ElringKlinger",
        contact_person="Julian Jurcevic",
        contact_email="julian@example.com",
        company_aliases=("ElringKlinger AG",),
    )
    anfrage = Anfrage(
        kunde_firma="ElringKlinger AG",
        kunde_ansprechpartner="Julian Jurcevic",
        kunde_email="Julian <julian@example.com>",
        positionen=[],
        header_evidence={
            "kunde_firma": Evidence(source_file="mail"),
            "kunde_ansprechpartner": Evidence(source_file="mail"),
            "kunde_email": Evidence(source_file="mail"),
        },
    )

    cleared = sanitize_own_customer_fields(anfrage, ctx)

    assert cleared == ["kunde_firma", "kunde_ansprechpartner", "kunde_email"]
    assert anfrage.kunde_firma is None
    assert anfrage.kunde_ansprechpartner is None
    assert anfrage.kunde_email is None
    assert "kunde_firma" not in anfrage.header_evidence
    assert "kunde_ansprechpartner" not in anfrage.header_evidence
    assert "kunde_email" not in anfrage.header_evidence
    assert anfrage.unsicherheiten


def test_sanitize_keeps_real_customer_values():
    ctx = OwnPartyContext(
        company_name="ElringKlinger",
        contact_person="Julian Jurcevic",
        contact_email="julian@example.com",
    )
    anfrage = Anfrage(
        kunde_firma="Musterkunde GmbH",
        kunde_ansprechpartner="Erika Musterfrau",
        kunde_email="erika@musterkunde.example",
        positionen=[],
    )

    cleared = sanitize_own_customer_fields(anfrage, ctx)

    assert cleared == []
    assert anfrage.kunde_firma == "Musterkunde GmbH"
    assert anfrage.kunde_ansprechpartner == "Erika Musterfrau"
    assert anfrage.kunde_email == "erika@musterkunde.example"
