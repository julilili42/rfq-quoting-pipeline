from __future__ import annotations

from types import SimpleNamespace

from quoting.api import frontend_router
from quoting.extraction.llm.base import LLMResponse, TokenUsage
from quoting.reviews import Payloads


class _OkClient:
    def generate(self, *args, **kwargs):
        return LLMResponse(
            text='{"status":"ok"}',
            usage=TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10),
        )


class _FailingClient:
    def __init__(self, message: str):
        self._message = message

    def generate(self, *args, **kwargs):
        raise RuntimeError(self._message)


def test_probe_llm_provider_returns_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr(
        "quoting.extraction.llm.build_llm",
        lambda settings: _OkClient(),
    )

    result = frontend_router.probe_llm_provider()

    assert result.status == "ok"
    assert result.provider == "gemini"
    assert result.response_preview == '{"status":"ok"}'
    assert result.usage is not None
    assert result.usage.total_tokens == 10


def test_probe_llm_provider_returns_scrubbed_error(monkeypatch):
    secret = "test-google-key"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    monkeypatch.setattr(
        "quoting.extraction.llm.build_llm",
        lambda settings: _FailingClient(f"provider rejected key {secret}"),
    )

    result = frontend_router.probe_llm_provider()

    assert result.status == "error"
    assert result.error_type == "RuntimeError"
    assert secret not in result.detail
    assert "***" in result.detail


def test_recent_pipeline_failures_reads_latest_and_scrubs_secret(sqlite_repo):
    secret = "test-google-key"
    settings = SimpleNamespace(google_api_key=secret, nexus_api_key=None)

    sqlite_repo.create_review("older-review")
    sqlite_repo.save_payload(
        "older-review",
        Payloads.PROGRESS,
        {
            "status": "failed",
            "current_step": "Extraktion",
            "error": "old failure",
            "updated_at": "2026-05-01T10:00:00+00:00",
            "progress_percent": 20,
        },
    )

    sqlite_repo.create_review("newer-review")
    sqlite_repo.save_mail(
        "newer-review",
        {"subject": "RFQ 123", "from": "buyer@example.test"},
    )
    sqlite_repo.save_payload(
        "newer-review",
        Payloads.PROGRESS,
        {
            "status": "failed",
            "current_step": "Matching",
            "error": f"provider rejected {secret}",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "progress_percent": 60,
        },
    )

    summary = frontend_router._recent_pipeline_failures(settings)

    assert summary.total_failed == 2
    assert summary.recent[0].review_id == "newer-review"
    assert summary.recent[0].subject == "RFQ 123"
    assert secret not in summary.recent[0].error
    assert "***" in summary.recent[0].error


def test_stammdaten_quality_counts_pricing_and_identity_issues(tmp_path):
    csv_path = tmp_path / "stammdaten.csv"
    csv_path.write_text(
        "\n".join([
            "artikel_nr,bezeichnung,werkstoff,abmessungen,basispreis_eur,preis_min_eur,preis_max_eur,n_offers",
            "A1,Foo,PTFE,10x20,12.5,10,15,2",
            "A1,Foo duplicate,PTFE,10x20,13,10,15,1",
            "B2,Bar,,,0,0,5,1",
            ",Missing article,PTFE,1x2,4,5,3,2",
            "C3,,PTFE,1x2,4,3,5,2",
        ]),
        encoding="utf-8",
    )

    quality = frontend_router._stammdaten_quality(csv_path)

    assert quality is not None
    assert quality.total_rows == 5
    assert quality.duplicate_article_numbers == 1
    assert quality.missing_article_numbers == 1
    assert quality.missing_descriptions == 1
    assert quality.zero_or_missing_prices == 1
    assert quality.invalid_price_ranges == 1
    assert quality.single_offer_articles == 2
    assert quality.missing_materials == 1
    assert quality.missing_dimensions == 1
