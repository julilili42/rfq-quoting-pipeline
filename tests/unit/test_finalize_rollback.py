"""finalize_quotation must roll back the final PDF when the approval transition fails.

Without the rollback the filesystem ends up holding a freshly-built final PDF
while the approval payload still says the review is not approved — a state the
Outlook workflow cannot recover from gracefully.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from quoting.api import _common
from quoting.api.approval_store import ApprovalRecord, load_approval, save_approval
from quoting.api.routers import reviews as reviews_router
from quoting.api.routers.reviews import FinalizeRequest, finalize_quotation
from quoting.api.services.quality_gate_service import QualityGateResult, QualityIssue


@pytest.fixture
def review(sqlite_repo) -> tuple[str, Path]:
    review_id = "review-finalize"
    sqlite_repo.create_review(review_id)
    save_approval(review_id, ApprovalRecord(state="reviewed"))
    return review_id, sqlite_repo.artifact_dir(review_id)


def _patch_handler_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(_common, "_pipeline", MagicMock())

    monkeypatch.setattr(
        reviews_router,
        "_load_review_data",
        lambda *_a, **_k: (MagicMock(), [], []),
    )
    monkeypatch.setattr(
        reviews_router,
        "build_quotation_with_overrides",
        lambda *_a, **_k: MagicMock(),
    )
    monkeypatch.setattr(
        reviews_router,
        "evaluate_quality_gate",
        lambda *_a, **_k: QualityGateResult(blockers=[], warnings=[], stats={}),
    )

    def fake_build(_anfrage, _quotation, pdf_path, *, is_final, company_profile):
        Path(pdf_path).write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(reviews_router, "build_draft_pdf", fake_build)


def test_finalize_rolls_back_pdf_when_transition_fails(review, monkeypatch):
    review_id, folder = review
    _patch_handler_dependencies(monkeypatch)

    def failing_transition(*_args, **_kwargs):
        raise RuntimeError("simulated approval crash")

    monkeypatch.setattr(
        "quoting.api.approval_store.transition",
        failing_transition,
    )

    with pytest.raises(HTTPException) as exc_info:
        finalize_quotation(
            review_id,
            FinalizeRequest(actor="user", filename="Angebot_Test.pdf"),
        )

    assert exc_info.value.status_code == 500
    assert not (folder / "Angebot_Test.pdf").exists()
    assert load_approval(review_id).state == "reviewed"


def test_finalize_keeps_pdf_and_marks_approved_on_success(review, monkeypatch):
    review_id, folder = review
    _patch_handler_dependencies(monkeypatch)

    response = finalize_quotation(
        review_id,
        FinalizeRequest(actor="user", filename="Angebot_Test.pdf"),
    )

    assert response["final_pdf_path"] == "Angebot_Test.pdf"
    assert (folder / "Angebot_Test.pdf").exists()

    record = load_approval(review_id)
    assert record.state == "approved"
    assert record.final_pdf_path == "Angebot_Test.pdf"
    assert record.approved_by == "user"


def test_finalize_rejects_quality_issues_without_acknowledgement(review, monkeypatch):
    review_id, folder = review
    _patch_handler_dependencies(monkeypatch)

    monkeypatch.setattr(
        reviews_router,
        "evaluate_quality_gate",
        lambda *_a, **_k: QualityGateResult(
            blockers=[
                QualityIssue(
                    id="price:zero:1",
                    severity="blocker",
                    step="positions",
                    title="Pos 1: Preis ist 0,00 EUR",
                )
            ],
            warnings=[],
            stats={},
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        finalize_quotation(
            review_id,
            FinalizeRequest(actor="user", filename="Angebot_Test.pdf"),
        )

    assert exc_info.value.status_code == 409
    assert not (folder / "Angebot_Test.pdf").exists()
    assert load_approval(review_id).state == "reviewed"


def test_finalize_allows_acknowledged_exception_without_reason(review, monkeypatch):
    review_id, _ = review
    _patch_handler_dependencies(monkeypatch)

    monkeypatch.setattr(
        reviews_router,
        "evaluate_quality_gate",
        lambda *_a, **_k: QualityGateResult(
            blockers=[
                QualityIssue(
                    id="price:zero:1",
                    severity="blocker",
                    step="positions",
                    title="Pos 1: Preis ist 0,00 EUR",
                )
            ],
            warnings=[],
            stats={},
        ),
    )

    response = finalize_quotation(
        review_id,
        FinalizeRequest(
            actor="user",
            filename="Angebot_Test.pdf",
            warning_acknowledged=True,
        ),
    )

    assert response["final_pdf_path"] == "Angebot_Test.pdf"
    record = load_approval(review_id)
    assert record.state == "approved"
    assert record.warning_acknowledged is True
    assert record.exception_reason is None
