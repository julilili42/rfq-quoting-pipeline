"""Tests for offer PDF configuration."""
from __future__ import annotations

from quoting.output.pdf.offer.config import OfferPdfConfig


def test_draft_closing_uses_header_contact_person_as_signature():
    config = OfferPdfConfig(contact_person="Max Mustermann", is_final=False)

    closing = config.effective_closing()

    assert closing[-1] == "Max Mustermann"
    assert "[NAME / SIGNATUR]" not in closing


def test_final_closing_includes_header_contact_person_as_signature():
    config = OfferPdfConfig(contact_person="Max Mustermann", is_final=True)

    assert config.effective_closing() == (
        "Mit freundlichen Grüßen",
        "Max Mustermann",
    )
