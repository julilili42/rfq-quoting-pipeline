"""Tests for upload-driven review creation."""
from __future__ import annotations

import asyncio
import email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from quoting.api.container import reset_app_container
from quoting.api.job_queue import JobQueue
from quoting.api.services.upload_service import create_review_from_upload


@pytest.fixture(autouse=True)
def _reset_container():
    reset_app_container()
    yield
    reset_app_container()


def _upload_file(
    name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> UploadFile:
    return UploadFile(
        BytesIO(data),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def _create_review(file: UploadFile) -> str:
    return asyncio.run(create_review_from_upload(file))


def _mail_bytes(
    *,
    subject: str = "RFQ 2026",
    sender: str = "kunde@example.com",
    body: str = "Bitte um Angebot fuer 10 Stk.",
    attachments: list[tuple[str, bytes]] | None = None,
) -> bytes:
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg.attach(MIMEText(body, "plain"))
    for name, content in attachments or []:
        part = MIMEApplication(content, Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(part)
    return msg.as_bytes(policy=email.policy.SMTP)


def test_upload_persists_input_and_enqueues_pipeline(sqlite_repo):
    upload = _upload_file("rfq.pdf", b"%PDF-1.4 fake\n", "application/pdf")

    review_id = _create_review(upload)

    assert sqlite_repo.exists(review_id)
    mail = sqlite_repo.load_mail(review_id)
    assert mail is not None
    assert mail["subject"] == "rfq"
    assert mail["attachments"] == [
        {
            "name": "rfq.pdf",
            "contentType": "application/pdf",
            "size": len(b"%PDF-1.4 fake\n"),
        }
    ]
    assert sqlite_repo.current_document(review_id, kind="attachment", filename="rfq.pdf")
    assert sqlite_repo.current_document(review_id, kind="draft_pdf") is None

    progress = sqlite_repo.load_progress(review_id)
    assert progress is not None
    assert progress["status"] == "running"
    assert progress["current_step"] == "Extraktion"
    assert progress["steps"][0]["name"] == "Mail vorbereiten"
    assert progress["steps"][0]["status"] == "completed"

    jobs = JobQueue(sqlite_repo).list_for_review(review_id)
    assert [(job.step, job.status) for job in jobs] == [("extract", "pending")]


def test_upload_parses_mail_files_before_enqueue(sqlite_repo):
    eml = _mail_bytes(
        subject="Preisanfrage 2026-42",
        sender="Felix <felix@example.com>",
        body="Bitte bieten Sie 25 Stk. Artikel X an.",
        attachments=[("drawing.pdf", b"%PDF-1.4 drawing\n")],
    )
    upload = _upload_file("message.eml", eml, "message/rfc822")

    review_id = _create_review(upload)

    mail = sqlite_repo.load_mail(review_id)
    assert mail is not None
    assert mail["subject"] == "Preisanfrage 2026-42"
    assert "felix@example.com" in mail["from"]
    assert "25 Stk" in mail["body"]
    assert [att["name"] for att in mail["attachments"]] == ["drawing.pdf"]

    assert sqlite_repo.current_document(
        review_id,
        kind="original",
        filename="message.eml",
    )
    assert sqlite_repo.current_document(
        review_id,
        kind="attachment",
        filename="drawing.pdf",
    )

    jobs = JobQueue(sqlite_repo).list_for_review(review_id)
    assert [(job.step, job.status) for job in jobs] == [("extract", "pending")]
