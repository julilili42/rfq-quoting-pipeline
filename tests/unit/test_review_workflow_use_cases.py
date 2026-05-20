from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from quoting.api.approval_store import ApprovalRecord, ApprovalStore
from quoting.api.progress_store import ProgressStore
from quoting.api.services.quality_gate_service import QualityGateResult
from quoting.api.services.review_service import ReviewDataService
from quoting.api.settings_store import AppSettings
from quoting.api.use_cases.dtos import IncomingMailAttachment, IncomingMailReview
from quoting.api.use_cases.errors import UseCaseBadRequest, UseCaseFailure
from quoting.api.use_cases.review_workflow import (
    CreateReviewFromMailUseCase,
    FinalizeQuotationUseCase,
    RegenerateQuotationUseCase,
    ResetReviewUseCase,
)
from quoting.matching import MatchResult
from quoting.pricing import Quotation, QuotationItem
from quoting.reviews import draft_pdf_filename


class _Coordinator:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start_pipeline(self, review_id: str) -> None:
        self.started.append(review_id)


def _pipeline() -> SimpleNamespace:
    return SimpleNamespace(settings=SimpleNamespace(preise_path=Path("/does/not/exist.csv")))


def _quality_gate_without_issues(*_args) -> QualityGateResult:
    return QualityGateResult(blockers=[], warnings=[], stats={})


def _quotation() -> Quotation:
    return Quotation(
        kunde_firma="Testkunde GmbH",
        kunde_ansprechpartner="Max Mustermann",
        kunde_email="max@example.com",
        kundennummer="K-1",
        belegnummer="RFQ-1",
        incoterms="EXW",
        zahlungsbedingungen="30 Tage",
        items=[
            QuotationItem(
                pos_nr=10,
                artikel_nr="001GLP108015",
                bezeichnung="Gleitstück",
                menge=2,
                einheit="Stk",
                einzelpreis=100,
                rabatt_prozent=0,
                gesamtpreis=200,
                bemerkung="",
            )
        ],
        gesamtsumme=200,
        waehrung="EUR",
        warnungen=[],
    )


def _match() -> MatchResult:
    return MatchResult(
        pos_nr=10,
        status="exact",
        score=1.0,
        matched_artikelnr="001GLP108015",
        matched_bezeichnung="Gleitstück",
        matched_row={"artikel_nr": "001GLP108015", "bezeichnung": "Gleitstück"},
    )


def test_create_review_from_mail_persists_input_and_starts_pipeline(sqlite_repo):
    coordinator = _Coordinator()
    attachment_body = b"PDF content"
    payload = IncomingMailReview(
        subject="Preisanfrage",
        sender="kunde@example.com",
        body="Bitte anbieten",
        outlook_item_id="outlook-1",
        attachments=[
            IncomingMailAttachment(
                name="../rfq.pdf",
                content_type="application/pdf",
                size=len(attachment_body),
                content_base64=base64.b64encode(attachment_body).decode("ascii"),
            )
        ],
    )

    response = CreateReviewFromMailUseCase(
        repo=sqlite_repo,
        progress_store=ProgressStore(sqlite_repo),
        approval_store=ApprovalStore(sqlite_repo),
        coordinator=coordinator,  # type: ignore[arg-type]
        review_ui_base_url="http://review.local",
    ).execute(payload)

    review_id = response["review_id"]
    assert coordinator.started == [review_id]
    assert response["status"] == "running"
    assert response["review_url"] == f"http://review.local?review_id={review_id}"

    review = sqlite_repo.get_review(review_id)
    assert review["subject"] == "Preisanfrage"
    assert review["sender"] == "kunde@example.com"
    assert review["source"] == "outlook"
    assert review["outlook_item_id"] == "outlook-1"

    assert sqlite_repo.load_mail(review_id)["attachments"][0]["name"] == "../rfq.pdf"
    saved_attachment = sqlite_repo.artifact_dir(review_id) / "rfq.pdf"
    assert saved_attachment.read_bytes() == attachment_body
    assert sqlite_repo.current_document(
        review_id,
        kind="attachment",
        filename="rfq.pdf",
    )

    progress = ProgressStore(sqlite_repo).read(review_id)
    assert progress["status"] == "running"
    assert progress["steps"][0]["name"] == "Mail vorbereiten"
    assert progress["steps"][0]["status"] == "completed"
    assert ApprovalStore(sqlite_repo).load(review_id).state == "draft_generated"


def test_create_review_from_mail_rejects_empty_mail(sqlite_repo):
    coordinator = _Coordinator()
    payload = IncomingMailReview(
        subject="",
        sender="kunde@example.com",
        body="",
        attachments=[],
    )

    with pytest.raises(UseCaseBadRequest) as exc_info:
        CreateReviewFromMailUseCase(
            repo=sqlite_repo,
            progress_store=ProgressStore(sqlite_repo),
            approval_store=ApprovalStore(sqlite_repo),
            coordinator=coordinator,  # type: ignore[arg-type]
            review_ui_base_url="http://review.local",
        ).execute(payload)

    assert "neither body text nor attachments" in str(exc_info.value)
    assert coordinator.started == []


def test_reset_review_rehydrates_mail_and_starts_pipeline(sqlite_repo):
    review_id = "review-reset"
    sqlite_repo.create_review(review_id)
    sqlite_repo.save_mail(
        review_id,
        {"subject": "Anfrage", "from": "kunde@example.com", "body": "Bitte anbieten"},
    )
    sqlite_repo.save_extracted(review_id, {"positionen": []})
    ProgressStore(sqlite_repo).complete(review_id, {"ok": True})
    ApprovalStore(sqlite_repo).save(review_id, ApprovalRecord(state="approved"))
    coordinator = _Coordinator()

    response = ResetReviewUseCase(
        repo=sqlite_repo,
        progress_store=ProgressStore(sqlite_repo),
        approval_store=ApprovalStore(sqlite_repo),
        review_data=ReviewDataService(sqlite_repo),
        coordinator=coordinator,  # type: ignore[arg-type]
    ).execute(review_id)

    assert response["review_id"] == review_id
    assert response["status"] == "running"
    assert coordinator.started == [review_id]
    assert sqlite_repo.load_extracted(review_id) is None
    assert ProgressStore(sqlite_repo).read(review_id)["status"] == "running"
    assert ApprovalStore(sqlite_repo).load(review_id).state == "draft_generated"


def test_regenerate_quotation_writes_draft_pdf_and_reviewed_quotation(
    sqlite_repo,
    sample_anfrage,
):
    review_id = "review-regenerate"
    sqlite_repo.create_review(review_id)
    calls: dict[str, object] = {}

    def load_review_data(received_review_id, received_pipeline):
        calls["loader"] = (received_review_id, received_pipeline)
        return sample_anfrage, [_match()], [{"type": "discount"}]

    def build_quotation(anfrage, matches, overrides, prices_path, received_review_id):
        calls["builder"] = (anfrage, matches, overrides, prices_path, received_review_id)
        return _quotation()

    def build_pdf(anfrage, quotation, pdf_path, *, is_final, company_profile):
        calls["pdf"] = (anfrage, quotation, pdf_path, is_final, company_profile)
        Path(pdf_path).write_bytes(b"%PDF draft")

    pipeline = _pipeline()
    result = RegenerateQuotationUseCase(
        repo=sqlite_repo,
        pipeline=pipeline,  # type: ignore[arg-type]
        settings_loader=AppSettings,
        review_data_loader=load_review_data,
        review_data=ReviewDataService(sqlite_repo),
        quotation_builder=build_quotation,
        pdf_builder=build_pdf,
    ).execute(review_id)

    assert result["gesamtsumme"] == 200
    assert calls["loader"] == (review_id, pipeline)
    assert calls["builder"][4] == review_id
    assert calls["pdf"][3] is False
    assert sqlite_repo.current_document(review_id, kind="draft_pdf")[
        "filename"
    ] == draft_pdf_filename(review_id)
    assert sqlite_repo.load_quotation_reviewed(review_id)["gesamtsumme"] == 200


def test_finalize_quotation_writes_final_pdf_and_approves_review(
    sqlite_repo,
    sample_anfrage,
):
    review_id = "review-finalize"
    sqlite_repo.create_review(review_id)

    def load_review_data(_review_id, _pipeline):
        return sample_anfrage, [_match()], []

    def build_pdf(_anfrage, _quotation, pdf_path, *, is_final, company_profile):
        assert is_final is True
        Path(pdf_path).write_bytes(b"%PDF final")

    response = FinalizeQuotationUseCase(
        repo=sqlite_repo,
        pipeline=_pipeline(),  # type: ignore[arg-type]
        settings_loader=AppSettings,
        review_data_loader=load_review_data,
        review_data=ReviewDataService(sqlite_repo),
        quotation_builder=lambda *_args: _quotation(),
        quality_gate_evaluator=_quality_gate_without_issues,
        pdf_builder=build_pdf,
        approval_store=ApprovalStore(sqlite_repo),
    ).execute(
        review_id,
        actor="user@example.com",
        filename="Angebot_Test.pdf",
        warning_acknowledged=False,
        exception_reason=None,
    )

    assert response == {"final_pdf_path": "Angebot_Test.pdf"}
    assert (sqlite_repo.artifact_dir(review_id) / "Angebot_Test.pdf").read_bytes() == b"%PDF final"
    assert sqlite_repo.current_document(
        review_id,
        kind="final_pdf",
        filename="Angebot_Test.pdf",
    )
    record = ApprovalStore(sqlite_repo).load(review_id)
    assert record.state == "approved"
    assert record.approved_by == "user@example.com"
    assert record.final_pdf_path == "Angebot_Test.pdf"


def test_finalize_quotation_rolls_back_pdf_when_approval_transition_fails(
    sqlite_repo,
    sample_anfrage,
):
    review_id = "review-finalize-rollback"
    sqlite_repo.create_review(review_id)

    def load_review_data(_review_id, _pipeline):
        return sample_anfrage, [_match()], []

    def build_pdf(_anfrage, _quotation, pdf_path, *, is_final, company_profile):
        Path(pdf_path).write_bytes(b"%PDF final")

    def fail_transition(*_args, **_kwargs):
        raise RuntimeError("transition failed")

    with pytest.raises(UseCaseFailure) as exc_info:
        FinalizeQuotationUseCase(
            repo=sqlite_repo,
            pipeline=_pipeline(),  # type: ignore[arg-type]
            settings_loader=AppSettings,
            review_data_loader=load_review_data,
            review_data=ReviewDataService(sqlite_repo),
            quotation_builder=lambda *_args: _quotation(),
            quality_gate_evaluator=_quality_gate_without_issues,
            pdf_builder=build_pdf,
            approval_store=ApprovalStore(sqlite_repo),
            approval_transition=fail_transition,
        ).execute(
            review_id,
            actor="user@example.com",
            filename="Angebot_Test.pdf",
            warning_acknowledged=False,
            exception_reason=None,
        )

    assert "Status-Übergang fehlgeschlagen" in str(exc_info.value)
    assert not (sqlite_repo.artifact_dir(review_id) / "Angebot_Test.pdf").exists()
    assert sqlite_repo.current_document(
        review_id,
        kind="final_pdf",
        filename="Angebot_Test.pdf",
    ) is None
