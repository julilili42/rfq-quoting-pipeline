"""Tests for quoting.ingestion.mail — parse_eml, mail_from_file, _html_to_text."""
from __future__ import annotations

import email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from quoting.ingestion.mail import _html_to_text, mail_from_file, parse_mail

# ---------- helpers ----------

def _write_eml(tmp_path: Path, subject="Test", sender="a@b.com",
               body_text="Hello", attachments=None) -> Path:
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg.attach(MIMEText(body_text, "plain"))
    for name, content in (attachments or []):
        att = MIMEApplication(content, Name=name)
        att["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(att)
    p = tmp_path / "test.eml"
    p.write_bytes(msg.as_bytes(policy=email.policy.SMTP))
    return p


# ---------- mail_from_file ----------

def test_mail_from_file_wraps_single_file(tmp_path):
    pdf = tmp_path / "rfq.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    mail = mail_from_file(pdf)
    assert mail.subject == "rfq.pdf"
    assert mail.attachments == [pdf]
    assert mail.body == ""


# ---------- parse_mail (.eml) ----------

def test_parse_eml_extracts_subject_and_sender(tmp_path):
    eml = _write_eml(tmp_path, subject="Anfrage 2024", sender="kunde@firma.de")
    mail = parse_mail(eml, tmp_path)
    assert mail.subject == "Anfrage 2024"
    assert "kunde@firma.de" in mail.sender


def test_parse_eml_extracts_body(tmp_path):
    eml = _write_eml(tmp_path, body_text="Bitte um Angebot für 500 Stk.")
    mail = parse_mail(eml, tmp_path)
    assert "Angebot" in mail.body


def test_parse_eml_no_attachments(tmp_path):
    eml = _write_eml(tmp_path)
    mail = parse_mail(eml, tmp_path)
    assert mail.attachments == []


def test_parse_eml_saves_attachment_to_disk(tmp_path):
    content = b"%PDF-1.4 fake pdf content"
    eml = _write_eml(tmp_path, attachments=[("invoice.pdf", content)])
    mail = parse_mail(eml, tmp_path)
    assert len(mail.attachments) == 1
    assert mail.attachments[0].name == "invoice.pdf"
    assert mail.attachments[0].read_bytes() == content


def test_parse_eml_multiple_attachments(tmp_path):
    attachments = [("a.pdf", b"aaa"), ("b.xlsx", b"bbb")]
    eml = _write_eml(tmp_path, attachments=attachments)
    mail = parse_mail(eml, tmp_path)
    names = {a.name for a in mail.attachments}
    assert names == {"a.pdf", "b.xlsx"}


def test_mail_has_content_with_body(tmp_path):
    eml = _write_eml(tmp_path, body_text="some body")
    mail = parse_mail(eml, tmp_path)
    assert mail.has_content


def test_mail_has_content_with_attachment(tmp_path):
    eml = _write_eml(tmp_path, body_text="", attachments=[("x.pdf", b"data")])
    mail = parse_mail(eml, tmp_path)
    assert mail.has_content


# ---------- _html_to_text ----------

def test_html_to_text_strips_tags():
    html = "<p>Hello <b>World</b></p>"
    result = _html_to_text(html)
    assert "Hello" in result
    assert "World" in result
    assert "<" not in result


def test_html_to_text_empty_returns_empty():
    assert _html_to_text("") == ""


def test_html_to_text_plain_text_passthrough():
    assert _html_to_text("no tags here") == "no tags here"


def test_html_to_text_handles_entities():
    html = "<p>5 &lt; 10 &amp; true</p>"
    result = _html_to_text(html)
    assert result  # must not crash
