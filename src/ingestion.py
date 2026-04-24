"""
Ingestion-Modul
===============
Trennt eingehende Preisanfragen in Mail-Body + Attachments.
Unterstützt .eml, .pdf, .xlsx, .xls, .csv direkt.
"""
from pathlib import Path
from typing import TypedDict
import email
from email import policy
from email.parser import BytesParser
import tempfile


class MailData(TypedDict):
    subject: str
    sender: str
    body: str
    attachments: list[Path]


def erkenne_dateityp(pfad: Path) -> str:
    """Ermittelt Dateityp über Extension + Content-Sniffing."""
    ext = pfad.suffix.lower().lstrip(".")
    if ext in ("eml", "msg"):
        return "eml"
    if ext == "pdf":
        return "pdf"
    if ext in ("xlsx", "xls"):
        return "xlsx"
    if ext == "csv":
        return "csv"
    return ext or "unknown"


def parse_mail(eml_pfad: Path, temp_dir: Path | None = None) -> MailData:
    """
    Parst .eml-Datei -> Body + Attachments als Pfade.
    Attachments werden in temp_dir (oder System-Temp) gespeichert.
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="eml_att_"))
    else:
        temp_dir.mkdir(parents=True, exist_ok=True)

    with open(eml_pfad, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    subject = msg.get("Subject", "")
    sender = msg.get("From", "")

    # Body extrahieren (bevorzugt text/plain, sonst HTML)
    body_text = ""
    body_html = ""
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition") or "")
        if "attachment" in disp:
            continue
        if ctype == "text/plain" and not body_text:
            body_text = part.get_content()
        elif ctype == "text/html" and not body_html:
            body_html = part.get_content()

    body = body_text or _html_to_text(body_html)

    # Attachments extrahieren
    attachments: list[Path] = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        if not filename:
            continue
        # Safe filename (keine Pfad-Traversal)
        safe_name = Path(filename).name
        target = temp_dir / safe_name
        payload = part.get_payload(decode=True)
        if payload:
            target.write_bytes(payload)
            attachments.append(target)

    return MailData(
        subject=subject,
        sender=sender,
        body=body,
        attachments=attachments,
    )


def _html_to_text(html: str) -> str:
    """Minimaler HTML->Text Fallback (ohne externe Dependencies)."""
    if not html:
        return ""
    try:
        from html.parser import HTMLParser

        class Stripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data):
                self.parts.append(data)

        s = Stripper()
        s.feed(html)
        return "\n".join(p.strip() for p in s.parts if p.strip())
    except Exception:
        return html
