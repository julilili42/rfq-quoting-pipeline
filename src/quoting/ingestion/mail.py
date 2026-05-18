"""Unified Mail data structure + parsers for .eml / .msg / loose files.

The Mail object is the *only* input the pipeline accepts. Every entry point
(API, CLI, tests) builds a Mail and hands it to QuotingPipeline.run().
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path


@dataclass
class Mail:
    """Everything the pipeline needs to know about an incoming RFQ.

    Attachments are concrete file paths on disk. Whoever builds the Mail is
    responsible for writing attachment bytes to a real location (temp dir,
    review folder, etc.) — the pipeline only reads from `attachments`.
    """
    subject: str = ""
    sender: str = ""
    body: str = ""
    attachments: list[Path] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """True if there's anything for the LLM to look at."""
        return bool(self.attachments) or bool(self.body.strip())


# Backwards-compat alias — older code imported `MailData`.
MailData = Mail


def parse_mail(mail_path: Path, temp_dir: Path | None = None) -> Mail:
    """Parse .eml or .msg into a Mail. Attachments are written to temp_dir."""
    suffix = mail_path.suffix.lower()
    if suffix == ".msg":
        return _parse_msg(mail_path, temp_dir)
    return _parse_eml(mail_path, temp_dir)


def mail_from_file(path: Path) -> Mail:
    """Wrap a single non-mail file (PDF/XLSX/CSV/...) as a Mail with no body.

    Useful for CLI usage where the user passes a bare attachment instead of
    a full mail.
    """
    return Mail(
        subject=path.name,
        sender="",
        body="",
        attachments=[path],
    )


# ---------- internals ----------


def _unique_path(directory: Path, filename: str) -> Path:
    """Return a path inside directory that does not collide with existing files."""
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while target.exists():
        target = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return target


def _parse_eml(eml_path: Path, temp_dir: Path | None = None) -> Mail:
    target_dir = temp_dir or Path(tempfile.mkdtemp(prefix="eml_att_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    with open(eml_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

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

    attachments: list[Path] = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        if not filename:
            continue
        safe_name = Path(filename).name
        target = _unique_path(target_dir, safe_name)
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes) and payload:
            target.write_bytes(payload)
            attachments.append(target)

    return Mail(
        subject=msg.get("Subject", "") or "",
        sender=msg.get("From", "") or "",
        body=body,
        attachments=attachments,
    )


def _parse_msg(msg_path: Path, temp_dir: Path | None = None) -> Mail:
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
        body = msg.body or _html_to_text(msg.htmlBody or "")
        attachments: list[Path] = []
        for att in msg.attachments:
            if not att.data:
                continue
            filename = att.longFilename or att.shortFilename or "attachment"
            safe_name = Path(filename).name
            target = _unique_path(target_dir, safe_name)
            target.write_bytes(att.data)
            attachments.append(target)

        return Mail(
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
    if not html:
        return ""
    try:
        stripper = _TextStripper()
        stripper.feed(html)
        return "\n".join(p.strip() for p in stripper.parts if p.strip())
    except (AttributeError, TypeError):
        return html
