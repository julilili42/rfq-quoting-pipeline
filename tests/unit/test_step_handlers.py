"""Tests for the idempotent pipeline step handlers.

Each handler is exercised in three modes:

1. **Fresh run** — no prior output for this review_id. The handler
   should call into the pipeline step and persist its output. We use a
   fake pipeline that records the call instead of running the real
   step (so the LLM and ReportLab stay out of the test path).
2. **Idempotent skip** — the handler is called when the expected
   output already exists. It should short-circuit and not invoke the
   pipeline step.
3. **Missing prerequisite** — the handler is called without its
   upstream payload. It should raise :class:`StepInputMissing` so the
   worker reports a clear, actionable error.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quoting.api.progress_store import ProgressStore
from quoting.api.step_handlers import StepHandlers, StepInputMissing
from quoting.core import Anfrage, Position
from quoting.extraction.llm.base import TokenUsage
from quoting.matching import MatchResult
from quoting.pipeline import StepContext
from quoting.pricing import Quotation
from quoting.reviews.quotation_store import quotation_from_dict

# ----------------------------------------------------------------- fixtures


@pytest.fixture
def review_id(sqlite_repo) -> str:
    sqlite_repo.create_review("review-1", subject="Anfrage", sender="kunde@example.com")
    return "review-1"


@pytest.fixture
def progress_store(sqlite_repo) -> ProgressStore:
    return ProgressStore(sqlite_repo)


def _make_anfrage() -> Anfrage:
    return Anfrage(
        kunde_firma="ACME GmbH",
        positionen=[
            Position(
                pos_nr=1,
                artikelnummer="X-001",
                bezeichnung="Test",
                menge=10,
                einheit="Stk",
                confidence="high",
                source_quote="q",
            )
        ],
    )


def _make_match(pos_nr: int = 1) -> MatchResult:
    return MatchResult(
        pos_nr=pos_nr,
        status="exact",
        score=1.0,
        matched_artikelnr="X-001",
        matched_bezeichnung="Test",
        matched_row={"artikel_nr": "X-001"},
    )


def _make_quotation() -> Quotation:
    """Build a Quotation via the dict→model helper used by the real code."""
    return quotation_from_dict(
        {
            "positionen": [
                {
                    "pos_nr": 1,
                    "artikelnummer": "X-001",
                    "bezeichnung": "Test",
                    "menge": 10,
                    "einheit": "Stk",
                    "einzelpreis": 5.0,
                    "gesamtpreis": 50.0,
                }
            ],
            "gesamtsumme": 50.0,
            "waehrung": "EUR",
        }
    )


class _FakePipeline:
    """Minimal QuotingPipeline stub that records calls and side-effects.

    The handlers persist payloads through the StepContext.snapshot_sink,
    so this fake just needs to invoke that sink the same way the real
    steps would.
    """

    def __init__(self):
        self.calls: list[str] = []

    def extract(self, mail, ctx: StepContext):
        self.calls.append("extract")
        anfrage = _make_anfrage()
        ctx.extra["extraction_path"] = "llm"
        ctx.extra["token_usage"] = TokenUsage(
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
        )
        ctx.snapshot_sink("extracted", anfrage.model_dump(mode="json"))
        ctx.report("Extraktion", "completed", f"{len(anfrage.positionen)} Positionen")
        return anfrage

    def match(self, anfrage, ctx: StepContext):
        self.calls.append("match")
        matches = [_make_match()]
        ctx.snapshot_sink("matches", [m.to_dict() for m in matches])
        return matches

    def price(self, anfrage, matches, ctx: StepContext):
        self.calls.append("price")
        quotation = _make_quotation()
        ctx.snapshot_sink("quotation", quotation.to_dict())
        return quotation

    def render(self, anfrage, quotation, output_path: Path, ctx, **kwargs):
        self.calls.append("render")
        output_path.write_bytes(b"%PDF-1.4 fake\n")
        return output_path


@pytest.fixture
def fake_pipeline() -> _FakePipeline:
    return _FakePipeline()


@pytest.fixture
def handlers(sqlite_repo, fake_pipeline, progress_store) -> StepHandlers:
    return StepHandlers(
        repo=sqlite_repo,
        pipeline=fake_pipeline,  # type: ignore[arg-type]
        progress_store=progress_store,
    )


# ----------------------------------------------------------- extract


def test_extract_runs_when_no_prior_output(handlers, fake_pipeline, sqlite_repo, review_id):
    sqlite_repo.save_mail(review_id, {"subject": "Anfrage", "from": "k@e.com", "body": "test"})

    handlers.extract(review_id)

    assert fake_pipeline.calls == ["extract"]
    assert sqlite_repo.load_extracted(review_id) is not None


def test_extract_records_llm_token_usage(handlers, sqlite_repo, review_id):
    sqlite_repo.save_mail(review_id, {"subject": "Anfrage", "from": "k@e.com", "body": "test"})

    handlers.extract(review_id)

    usage = sqlite_repo.load_llm_usage(review_id)
    assert usage["totals"] == {
        "input_tokens": 100,
        "output_tokens": 25,
        "total_tokens": 125,
    }
    assert usage["calls"][0]["source"] == "extraction"


def test_extract_records_extraction_path(handlers, sqlite_repo, review_id):
    sqlite_repo.save_mail(review_id, {"subject": "Anfrage", "from": "k@e.com", "body": "test"})

    handlers.extract(review_id)

    assert sqlite_repo.load_extraction_meta(review_id)["path"] == "llm"


def test_extract_skips_when_already_done(handlers, fake_pipeline, sqlite_repo, review_id):
    sqlite_repo.save_mail(review_id, {"subject": "x", "from": "k@e.com", "body": "test"})
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))

    handlers.extract(review_id)

    assert fake_pipeline.calls == []  # pipeline was not invoked


def test_extract_raises_when_mail_missing(handlers, review_id):
    with pytest.raises(StepInputMissing, match="mail payload"):
        handlers.extract(review_id)


def test_extract_raises_when_mail_has_no_content(handlers, sqlite_repo, review_id):
    sqlite_repo.save_mail(review_id, {"subject": "", "from": "", "body": ""})

    with pytest.raises(StepInputMissing, match="no body"):
        handlers.extract(review_id)


# ----------------------------------------------------------- match


def test_match_runs_when_anfrage_present_and_no_matches(
    handlers, fake_pipeline, sqlite_repo, review_id
):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))

    handlers.match(review_id)

    assert fake_pipeline.calls == ["match"]
    assert sqlite_repo.load_matches_initial(review_id) is not None


def test_match_skips_when_matches_initial_already_present(
    handlers, fake_pipeline, sqlite_repo, review_id
):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_matches_initial(review_id, [_make_match().to_dict()])

    handlers.match(review_id)

    assert fake_pipeline.calls == []


def test_match_raises_when_anfrage_missing(handlers, review_id):
    with pytest.raises(StepInputMissing, match="anfrage"):
        handlers.match(review_id)


# ----------------------------------------------------------- price


def test_price_runs_with_anfrage_and_matches(handlers, fake_pipeline, sqlite_repo, review_id):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_matches_initial(review_id, [_make_match().to_dict()])

    handlers.price(review_id)

    assert fake_pipeline.calls == ["price"]
    assert sqlite_repo.load_quotation_initial(review_id) is not None


def test_price_skips_when_quotation_initial_present(
    handlers, fake_pipeline, sqlite_repo, review_id
):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_matches_initial(review_id, [_make_match().to_dict()])
    sqlite_repo.save_quotation_initial(review_id, _make_quotation().to_dict())

    handlers.price(review_id)

    assert fake_pipeline.calls == []


def test_price_raises_when_anfrage_missing(handlers, review_id):
    with pytest.raises(StepInputMissing, match="anfrage"):
        handlers.price(review_id)


def test_price_raises_when_matches_missing(handlers, sqlite_repo, review_id):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))

    with pytest.raises(StepInputMissing, match="matches"):
        handlers.price(review_id)


# ----------------------------------------------------------- render


def test_render_runs_with_quotation(handlers, fake_pipeline, sqlite_repo, review_id):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_quotation_initial(review_id, _make_quotation().to_dict())

    handlers.render(review_id)

    assert fake_pipeline.calls == ["render"]
    doc = sqlite_repo.current_document(review_id, kind="draft_pdf")
    assert doc is not None
    assert Path(doc["storage_path"]).exists()


def test_render_skips_when_pdf_already_exists(
    handlers, fake_pipeline, sqlite_repo, review_id
):
    """Both DB row and file on disk must be present for skip."""
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_quotation_initial(review_id, _make_quotation().to_dict())

    handlers.render(review_id)
    assert fake_pipeline.calls == ["render"]

    handlers.render(review_id)  # second call should skip
    assert fake_pipeline.calls == ["render"]  # unchanged


def test_render_re_runs_when_pdf_file_was_removed(
    handlers, fake_pipeline, sqlite_repo, review_id
):
    """A DB row pointing at a missing file shouldn't fool the skip-check."""
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))
    sqlite_repo.save_quotation_initial(review_id, _make_quotation().to_dict())

    handlers.render(review_id)
    pdf_path = Path(
        sqlite_repo.current_document(review_id, kind="draft_pdf")["storage_path"]
    )
    pdf_path.unlink()  # disk and DB drift apart

    handlers.render(review_id)
    assert fake_pipeline.calls == ["render", "render"]
    assert pdf_path.exists()


def test_render_raises_when_quotation_missing(handlers, sqlite_repo, review_id):
    sqlite_repo.save_extracted(review_id, _make_anfrage().model_dump(mode="json"))

    with pytest.raises(StepInputMissing, match="quotation"):
        handlers.render(review_id)


# --------------------------------------------------- progress reporting


def test_extract_reports_progress(handlers, sqlite_repo, progress_store, review_id):
    progress_store.init(review_id)
    sqlite_repo.save_mail(review_id, {"subject": "x", "from": "k@e.com", "body": "test"})

    handlers.extract(review_id)

    progress = progress_store.read(review_id)
    assert progress is not None
    step = next(s for s in progress["steps"] if s["name"] == "Extraktion")
    assert step["status"] == "completed"
