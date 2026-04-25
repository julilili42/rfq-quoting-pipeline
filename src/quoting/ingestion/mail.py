"""Parse .eml and .msg files into body + attachment paths."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path


@dataclass
class MailData:
    subject: str
    sender: str
    body: str
    attachments: list[Path]


def parse_mail(mail_path: Path, temp_dir: Path | None = None) -> MailData:
    """Parse .eml or .msg -> body + attachments written to temp_dir."""
    suffix = mail_path.suffix.lower()

    if suffix == ".msg":
        return _parse_msg(mail_path, temp_dir)
    else:
        return _parse_eml(mail_path, temp_dir)


def _parse_eml(eml_path: Path, temp_dir: Path | None = None) -> MailData:
    """Parse .eml -> body + attachments written to temp_dir."""
    target_dir = temp_dir or Path(tempfile.mkdtemp(prefix="eml_att_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    with open(eml_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    # Body: prefer text/plain, fall back to stripped HTML
    body_text = ""
    body_html = ""
    for part in msg.walk():
        disp = str(part.get("Content-Disposition") or "")
        if "attachment" in disp:
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not body_text:
            body_text = part.get_content()
        elif ctype == "text/html" and not body_html:
            body_html = part.get_content()
    body = body_text or _html_to_text(body_html)

    # Attachments: safe filenames only (no path traversal)
    attachments: list[Path] = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        if not filename:
            continue
        safe_name = Path(filename).name
        target = target_dir / safe_name
        payload = part.get_payload(decode=True)
        if payload:
            target.write_bytes(payload)
            attachments.append(target)

    return MailData(
        subject=msg.get("Subject", ""),
        sender=msg.get("From", ""),
        body=body,
        attachments=attachments,
    )


def _parse_msg(msg_path: Path, temp_dir: Path | None = None) -> MailData:
    """Parse Outlook .msg -> body + attachments written to temp_dir.

    Requires: pip install extract-msg
    """
    try:
        import extract_msg
    except ImportError as e:
        raise ImportError(
            "Package 'extract-msg' is required for .msg support. "
            "Install it with: pip install extract-msg"
        ) from e

    target_dir = temp_dir or Path(tempfile.mkdtemp(prefix="msg_att_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    with extract_msg.openMsg(msg_path) as msg:
        # Body: prefer plain text, fall back to stripped HTML
        body = msg.body or _html_to_text(msg.htmlBody or "")

        attachments: list[Path] = []
        for att in msg.attachments:
            if not att.data:
                continue
            # longFilename falls back to shortFilename if not set
            filename = att.longFilename or att.shortFilename or "attachment"
            safe_name = Path(filename).name
            target = target_dir / safe_name
            target.write_bytes(att.data)
            attachments.append(target)

        return MailData(
            subject=msg.subject or "",
            sender=msg.sender or "",
            body=body,
            attachments=attachments,
        )


class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(html: str) -> str:
    """Minimal HTML -> text fallback (no external deps)."""
    if not html:
        return ""
    try:
        stripper = _TextStripper()
        stripper.feed(html)
        return "\n".join(p.strip() for p in stripper.parts if p.strip())
    except Exception:
        return html