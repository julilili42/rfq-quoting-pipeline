"""Integration tests for ExtractionStep with a mocked LLM client."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quoting.core import Anfrage, Settings
from quoting.extraction.extractor import ExtractionError
from quoting.extraction.llm.base import LLMResponse, TokenUsage
from quoting.ingestion import Mail
from quoting.pipeline.context import StepContext
from quoting.pipeline.steps.extract import ExtractionStep


def _minimal_anfrage_json(**overrides) -> str:
    data = {
        "positionen": [
            {
                "pos_nr": 10,
                "artikelnummer": "001GLP108015",
                "bezeichnung": "Gleitstück PTFE",
                "menge": 5,
                "einheit": "Stk",
                "confidence": "high",
                "source_quote": "Pos 10  001GLP108015  5 Stk",
                "source_file": "mail",
            }
        ],
    }
    data.update(overrides)
    return json.dumps(data)


def _make_step(mock_llm) -> ExtractionStep:
    settings = Settings(llm_provider="gemini", google_api_key="test")
    step = ExtractionStep(settings)
    # Patch build_llm so no real provider is instantiated
    import quoting.extraction.extractor as ext_module
    ext_module.build_llm = lambda _: mock_llm
    return step


def _make_mail(tmp_path: Path) -> Mail:
    csv = tmp_path / "rfq.csv"
    csv.write_text("pos;artikel;menge\n10;001GLP108015;5\n", encoding="utf-8")
    return Mail(
        subject="Test RFQ",
        body="Bitte um Angebot",
        sender="kunde@example.com",
        attachments=[csv],
    )


@pytest.fixture()
def ctx(tmp_path):
    return StepContext(work_dir=tmp_path)


def test_happy_path_returns_anfrage(tmp_path, ctx, monkeypatch):
    usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse(
        text=_minimal_anfrage_json(), usage=usage
    )

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = _make_mail(tmp_path)

    anfrage = step.run(mail, ctx)

    assert isinstance(anfrage, Anfrage)
    assert len(anfrage.positionen) == 1
    assert anfrage.positionen[0].artikelnummer == "001GLP108015"
    assert ctx.extra["token_usage"] == usage
    assert (tmp_path / "extracted.json").exists()


def test_llm_failure_raises_extraction_error(tmp_path, ctx, monkeypatch):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = ConnectionError("API unreachable")

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = _make_mail(tmp_path)

    with pytest.raises(ExtractionError, match="LLM call failed"):
        step.run(mail, ctx)


def test_malformed_json_raises_extraction_error(tmp_path, ctx, monkeypatch):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse(
        text="Sorry, I cannot process this document.", usage=None
    )

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = _make_mail(tmp_path)

    with pytest.raises(ExtractionError, match="no parseable JSON"):
        step.run(mail, ctx)


def test_invalid_schema_raises_extraction_error(tmp_path, ctx, monkeypatch):
    mock_llm = MagicMock()
    # Valid JSON but wrong schema (positionen missing required fields)
    mock_llm.generate.return_value = LLMResponse(
        text='{"positionen": [{"pos_nr": "not-a-number"}]}', usage=None
    )

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = _make_mail(tmp_path)

    with pytest.raises(ExtractionError, match="schema"):
        step.run(mail, ctx)


def test_empty_positionen_is_valid(tmp_path, ctx, monkeypatch):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse(
        text=_minimal_anfrage_json(positionen=[]), usage=None
    )

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = _make_mail(tmp_path)

    anfrage = step.run(mail, ctx)
    assert anfrage.positionen == []


def test_body_only_mail_no_attachments(tmp_path, ctx, monkeypatch):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse(
        text=_minimal_anfrage_json(), usage=None
    )

    monkeypatch.setattr("quoting.extraction.extractor.build_llm", lambda _: mock_llm)
    step = ExtractionStep(Settings(llm_provider="gemini", google_api_key="test"))
    mail = Mail(subject="S", body="Bitte 5x Gleitstück", sender="a@b.com", attachments=[])

    anfrage = step.run(mail, ctx)
    assert isinstance(anfrage, Anfrage)
