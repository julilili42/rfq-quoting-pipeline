"""LLM-generated cover-letter body for the Outlook reply.

Given the reviewed Anfrage + Quotation, produces a short complete plain-text
body in DE or EN. Used by the ``GET /reviews/{id}/reply-body`` endpoint when
the user enables the toggle on the /mail-vorlage page.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from ..core import Anforderung, Anfrage, get_logger
from ..extraction.llm.base import LLMClient, TokenUsage
from ..pricing import Quotation

log = get_logger()

Language = Literal["de", "en"]

_EN_HINTS = (
    "regards",
    "best regards",
    "kind regards",
    "dear sir",
    "dear madam",
    "request for quote",
    "request for quotation",
    "rfq",
    "please find",
    "thank you for",
    "could you please",
)
_DE_HINTS = (
    "sehr geehrte",
    "mit freundlichen",
    "anfrage",
    "angebot",
    "bitte um",
    "danke für",
)

_EXTRA_DOCUMENT_TERMS = (
    "abnahmeprüfzeugnis",
    "abnahmepruefzeugnis",
    "prüfzeugnis",
    "pruefzeugnis",
    "zertifikat",
    "zertifikate",
    "werkszeugnis",
    "zeichnung",
    "zeichnungen",
    "certificate",
    "certificates",
    "documentation",
    "drawing",
    "drawings",
    "inspection certificate",
)
_ATTACHMENT_CLAIM_TERMS = (
    "anhang",
    "anhäng",
    "anhaeng",
    "angehäng",
    "angehaeng",
    "anlage",
    "beigefügt",
    "beigefuegt",
    "beigelegt",
    "beilegen",
    "beilegend",
    "beiliegen",
    "beiliegend",
    "lege ich bei",
    "legen wir bei",
    "liegt bei",
    "liegen bei",
    "mitgesendet",
    "mitgeschickt",
    "mitsenden",
    "mitschicken",
    "als pdf",
    "attached",
    "attachment",
    "enclosed",
    "file",
    "files",
)
_DRAWING_FOLLOW_UP_TERMS = (
    "separat nach",
    "separat zu",
    "nachreich",
    "nachgereicht",
    "nachsenden",
    "nachgesendet",
    "separately later",
    "provide separately",
)


def detect_language(text: str) -> Language:
    """Heuristic DE/EN detection over a mail body.

    Looks for common salutation/closing keywords. Falls back to ``de``.
    """
    if not text:
        return "de"
    lowered = text.lower()
    de_score = sum(1 for h in _DE_HINTS if h in lowered)
    en_score = sum(1 for h in _EN_HINTS if h in lowered)
    if de_score == 0 and en_score == 0:
        ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(len(text), 1)
        return "en" if ascii_ratio > 0.97 and len(text) > 50 else "de"
    return "en" if en_score > de_score else "de"


def _format_positions_summary(quotation: Quotation, max_items: int = 5) -> str:
    items = quotation.items[:max_items]
    lines = []
    for it in items:
        line = f"- {it.menge:g} {it.einheit} {it.bezeichnung} (Pos. {it.pos_nr})"
        lines.append(line)
    if len(quotation.items) > max_items:
        lines.append(f"- … und {len(quotation.items) - max_items} weitere Positionen")
    return "\n".join(lines) if lines else "(keine Positionen)"


def _format_acknowledged_block(
    acknowledged: list[Anforderung],
    language: Language,
    outgoing_attachment_names: list[str] | None = None,
) -> str:
    if not acknowledged:
        return ""
    categories = {item.kategorie for item in acknowledged}
    outgoing_attachment_names = outgoing_attachment_names or []
    if language == "de":
        header = (
            "\nVom Vertrieb bestätigte Aufgaben aus der Anfrage "
            "(nicht automatisch alle erwähnen; nutze die Leitplanken unten):\n"
        )
        lines = [
            f"- [{_requirement_label(item.kategorie, language)}"
            f"{_format_requirement_position(item)}] {item.text}"
            for item in acknowledged
        ]
    else:
        header = (
            "\nCustomer tasks confirmed by Sales "
            "(do not automatically mention all of them; follow the guidance below):\n"
        )
        lines = [
            f"- [{_requirement_label(item.kategorie, language)}"
            f"{_format_requirement_position(item)}] {item.text}"
            for item in acknowledged
        ]
    return header + "\n".join(lines) + _format_requirement_guidance(
        categories,
        language,
        outgoing_attachment_names=outgoing_attachment_names,
    )


def _requirement_label(category: str, language: Language) -> str:
    labels = {
        "de": {
            "zeichnung": "Zeichnung",
            "zertifikat": "Zertifikat",
            "verpackung": "Verpackung",
            "logistik": "Logistik",
            "termin": "Termin",
            "sonstige": "Sonstige",
        },
        "en": {
            "zeichnung": "drawing",
            "zertifikat": "certificate",
            "verpackung": "packaging",
            "logistik": "logistics",
            "termin": "deadline",
            "sonstige": "other",
        },
    }
    return labels[language].get(category, category)


def _format_requirement_position(item: Anforderung) -> str:
    return f", Pos. {item.pos_nr}" if item.pos_nr is not None else ""


def _format_outgoing_attachments(
    outgoing_attachment_names: list[str] | None,
    language: Language,
) -> str:
    names = [name.strip() for name in outgoing_attachment_names or [] if name.strip()]
    if not names:
        return "- keine" if language == "de" else "- none"
    return "\n".join(f"- {name}" for name in names)


def _format_requirement_guidance(
    categories: set[str],
    language: Language,
    outgoing_attachment_names: list[str],
) -> str:
    has_outgoing_attachments = bool(outgoing_attachment_names)
    if language == "de":
        lines = ["\n\nMail-Body-Leitplanken zu diesen Aufgaben:"]
        if categories & {"sonstige", "termin"}:
            lines.append(
                "- Preis-/Lieferzeitaufgaben: Du darfst sagen, dass aktuelle "
                "Preise und genannte Lieferzeiten im Angebot stehen; keine "
                "Beträge im Fließtext nennen."
            )
        if "verpackung" in categories:
            lines.append(
                "- Verpackung/Gewicht: Nur allgemein als berücksichtigt erwähnen, "
                "wenn es zum Angebot passt; keine Verpackungs- oder Gewichtswerte "
                "erfinden."
            )
        if "logistik" in categories:
            lines.append(
                "- Logistikvorgaben: Nur allgemein als berücksichtigt erwähnen; "
                "keine neuen Versand- oder Lieferzusagen erfinden."
            )
        if categories & {"zeichnung", "zertifikat"}:
            if has_outgoing_attachments:
                lines.append(
                    "- Zeichnungen: Wenn eine Zeichnungsaufgabe bestätigt ist, erwähne "
                    "sie in einem kurzen Satz als Bestandteil dieser Angebotsmail. "
                    "Erlaubte Formulierung: 'Die aktuell gültigen Zeichnungen "
                    "erhalten Sie ebenfalls mit dieser E-Mail.' Schreibe nicht, "
                    "dass Zeichnungen separat oder später nachgereicht werden."
                )
            else:
                lines.append(
                    "- Zeichnungen: Nicht im Mailtext erwähnen, solange keine "
                    "Zusatzanhänge für die Angebotsmail hinterlegt sind."
                )
            lines.append(
                "- Zertifikate und Prüfzeugnisse: Nur erwähnen, wenn sie durch das "
                "Angebot selbst abgedeckt sind; niemals als angehängte oder "
                "beigelegte Datei formulieren. Wenn unklar, weglassen."
            )
        return "\n".join(lines) + "\n"

    lines = ["\n\nEmail-body guidance for these tasks:"]
    if categories & {"sonstige", "termin"}:
        lines.append(
            "- Price/lead-time tasks: You may say that current prices and stated "
            "lead times are included in the quotation; do not mention amounts in "
            "the body."
        )
    if "verpackung" in categories:
        lines.append(
            "- Packaging/weight: Mention only generally that it is reflected if "
            "that fits the quotation; do not invent packaging or weight values."
        )
    if "logistik" in categories:
        lines.append(
            "- Logistics requirements: Mention only generally that they are "
            "reflected; do not invent shipping or delivery commitments."
        )
    if categories & {"zeichnung", "zertifikat"}:
        if has_outgoing_attachments:
            lines.append(
                "- Drawings: If a drawing task is confirmed, mention it in one short "
                "sentence as part of this quotation email. Allowed wording: 'You "
                "will also receive the current drawings with this email.' Do not say "
                "that drawings will be provided separately or later."
            )
        else:
            lines.append(
                "- Drawings: Do not mention them in the email body unless additional "
                "outgoing attachments have been uploaded for this quotation email."
            )
        lines.append(
            "- Certificates and inspection certificates: Mention them only if the "
            "quotation itself covers them; never describe them as attached or "
            "enclosed files. If unclear, omit them."
        )
    return "\n".join(lines) + "\n"


def build_reply_body_prompt(
    anfrage: Anfrage,
    quotation: Quotation,
    style_hint: str,
    language: Language,
    acknowledged_requirements: list[Anforderung] | None = None,
    outgoing_attachment_names: list[str] | None = None,
) -> str:
    """Construct the LLM prompt for the reply body."""
    firma = anfrage.kunde_firma or ""
    ansprechpartner = anfrage.kunde_ansprechpartner or ""
    positions_summary = _format_positions_summary(quotation)
    total = f"{quotation.gesamtsumme:,.2f} {quotation.waehrung}".replace(",", "X").replace(
        ".", ","
    ).replace("X", ".")
    lieferzeit_hinweise = sorted(
        {p.lieferzeit for p in anfrage.positionen if p.lieferzeit}
    )

    style_block = (
        f"\nStilvorgabe der Nutzer:in: {style_hint}\n" if style_hint.strip() else ""
    )
    acknowledged_block = _format_acknowledged_block(
        acknowledged_requirements or [],
        language,
        outgoing_attachment_names=outgoing_attachment_names,
    )

    if language == "de":
        return (
            "Du bist Vertriebs-Innendienst und schreibst eine kurze, höfliche Begleit-E-Mail "
            "zu einem PDF-Angebot. Gib NUR den vollständigen Mail-Body zurück — keine "
            "Betreffzeile, keine Erklärungen, keine Markdown-Formatierung.\n"
            "\n"
            "Regeln:\n"
            "- Beginne mit einer passenden Anrede in einer eigenen Zeile. Wenn kein "
            "Ansprechpartner sicher vorhanden ist: 'Sehr geehrte Damen und Herren,'.\n"
            "- Schreibe 3 bis 5 kurze, natürlich klingende Sätze als Hauptteil.\n"
            "- Nimm konkret Bezug auf die Anfrage, ohne eine unnatürliche Artikelliste zu bauen.\n"
            "- Erwähne, dass das Angebot als PDF anhängt.\n"
            "- Behaupte keine weiteren Anhänge außer dem Angebots-PDF. Auch wenn "
            "Positionen Zeichnungen, Zertifikate, Prüfzeugnisse oder Dokumentation "
            "enthalten, beschreibe sie nicht als PDF-Anhang oder Anlage; sie sind "
            "Angebotspositionen oder Kundenanforderungen.\n"
            "- Nenne Lieferzeiten nur, wenn sie als Lieferzeit-Hinweis unten vorhanden sind.\n"
            "- Keine Marketing-Floskeln, keine Preisnennung im Fließtext.\n"
            "- Schließe mit 'Mit freundlichen Grüßen' und darunter '[Absender]'.\n"
            "- Plain Text mit Absatzumbrüchen; keine Aufzählungen, keine Überschriften, "
            "keine umschließenden Anführungszeichen.\n"
            "- Gib wirklich nur den Mail-Text zurück. Kein JSON, kein Feldname wie "
            "email_body, keine Objektklammern.\n"
            "- Setze eine Leerzeile nach der Anrede und eine Leerzeile vor der Grußformel.\n"
            "- Verwende echte Zeilenumbrüche. Schreibe niemals die Zeichenfolge \\n in den Text.\n"
            "- Vermeide steife Formulierungen wie 'bezüglich', 'entsprechend' oder "
            "'hiermit übersenden wir'.\n"
            f"{style_block}"
            f"{acknowledged_block}"
            "\n"
            f"Kunde: {firma}\n"
            f"Ansprechpartner: {ansprechpartner}\n"
            f"Anzahl Positionen: {len(quotation.items)}\n"
            f"Gesamtsumme (nicht im Text nennen): {total}\n"
            f"Lieferzeit-Hinweise: {', '.join(lieferzeit_hinweise) if lieferzeit_hinweise else '–'}\n"
            "Zusatzanhänge für diese Angebotsmail:\n"
            f"{_format_outgoing_attachments(outgoing_attachment_names, language)}\n"
            "Positionen (Angebotspositionen, keine E-Mail-Anhänge):\n"
            f"{positions_summary}\n"
            "\n"
            "Beispiel (anderer Fall):\n"
            "Sehr geehrte Damen und Herren,\n\n"
            "vielen Dank für Ihre Anfrage zu den drei Hydraulikpumpen. Anbei erhalten "
            "Sie unser Angebot als PDF. Alle genannten Positionen sind zu den "
            "aufgeführten Konditionen lieferbar. Bei Rückfragen zur Lieferzeit oder "
            "zu einzelnen Positionen stehen wir Ihnen gern zur Verfügung.\n\n"
            "Mit freundlichen Grüßen\n"
            "[Absender]\n"
            "\n"
            "Antwort:"
        )

    return (
        "You are an inside-sales rep writing a short, polite cover note for a quotation PDF. "
        "Return ONLY the complete email body — no subject line, no explanations, no Markdown.\n"
        "\n"
        "Rules:\n"
        "- Start with a suitable salutation on its own line. If no contact is clearly known, "
        "use 'Dear Sir or Madam,'.\n"
        "- Write 3 to 5 short, natural body sentences.\n"
        "- Reference the request specifically without turning the positions into a clumsy list.\n"
        "- Mention the attached PDF quotation.\n"
        "- Do not claim any attachments other than the quotation PDF. Even if positions "
        "contain drawings, certificates, inspection certificates, or documentation, do "
        "not describe them as attached PDFs or files; they are quotation line items or "
        "customer requirements.\n"
        "- Mention delivery times only if they are listed below.\n"
        "- No marketing fluff, no price mentions in the body.\n"
        "- Close with 'Best regards' followed by '[Absender]' on the next line.\n"
        "- Plain text with paragraph breaks; no bullet lists, no headings, no surrounding quotes.\n"
        "- Return the actual email text only. No JSON, no field names such as email_body, "
        "no object braces.\n"
        "- Put a blank line after the salutation and a blank line before the closing.\n"
        "- Use real line breaks. Never write the literal sequence \\n in the body.\n"
        "- Avoid stiff phrases such as 'with regard to', 'corresponding', or 'we hereby send'.\n"
        f"{style_block}"
        f"{acknowledged_block}"
        "\n"
        f"Customer: {firma}\n"
        f"Contact: {ansprechpartner}\n"
        f"Number of positions: {len(quotation.items)}\n"
        f"Total (do not mention in body): {total}\n"
        f"Delivery times: {', '.join(lieferzeit_hinweise) if lieferzeit_hinweise else '–'}\n"
        "Additional attachments for this quotation email:\n"
        f"{_format_outgoing_attachments(outgoing_attachment_names, language)}\n"
        "Positions (quotation line items, not email attachments):\n"
        f"{positions_summary}\n"
        "\n"
        "Example (different case):\n"
        "Dear Sir or Madam,\n\n"
        "Thank you for your inquiry regarding the three hydraulic pumps. Please find our "
        "quotation attached as a PDF. All requested items are available at the stated "
        "conditions. Should you have any questions about delivery times or individual "
        "positions, please do not hesitate to get in touch.\n\n"
        "Best regards\n"
        "[Absender]\n"
        "\n"
        "Response:"
    )


def _strip_response(text: str) -> str:
    """Remove common LLM wrapper artifacts and surrounding whitespace."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:text|markdown|html)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r"^(antwort|response)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = _unwrap_json_body(cleaned)
    cleaned = cleaned.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    cleaned = cleaned.strip()
    quote_pairs = {
        '"': '"',
        "'": "'",
        "„": "“",
        "“": "”",
        "‘": "’",
        "«": "»",
    }
    if len(cleaned) >= 2 and quote_pairs.get(cleaned[0]) == cleaned[-1]:
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r"^(antwort|response)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    return _normalize_email_layout(cleaned.strip())


def _unwrap_json_body(text: str) -> str:
    """Accept accidental JSON wrappers and return the contained body text."""
    if not text.startswith("{"):
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(
            r'"(?:body|email_body|mail_body|message)"\s*:\s*"([\s\S]*?)"\s*}?\s*$',
            text,
        )
        return match.group(1).strip() if match else text
    if not isinstance(payload, dict):
        return text
    for key in ("body", "email_body", "mail_body", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return text


def _normalize_email_layout(text: str) -> str:
    """Keep generated plain text usable when pasted directly into Outlook."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""

    if len(lines) > 1 and _looks_like_salutation(lines[0]) and lines[1].strip():
        lines.insert(1, "")

    closing_idx = next((idx for idx, line in enumerate(lines) if _is_closing(line)), None)
    if closing_idx is not None and closing_idx > 0 and lines[closing_idx - 1].strip():
        lines.insert(closing_idx, "")

    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        normalized.append("" if blank else line)
        previous_blank = blank
    return "\n".join(normalized).strip()


def _looks_like_salutation(line: str) -> bool:
    lowered = line.strip().casefold()
    return lowered.endswith(",") and (
        lowered.startswith("sehr geehrte")
        or lowered.startswith("sehr geehrter")
        or lowered.startswith("sehr geehrtes")
        or lowered.startswith("hallo")
        or lowered.startswith("guten tag")
        or lowered.startswith("dear ")
    )


def _is_closing(line: str) -> bool:
    lowered = line.strip().casefold()
    return lowered in {
        "mit freundlichen grüßen",
        "mit freundlichen grüssen",
        "mit freundlichen gruessen",
        "freundliche grüße",
        "freundliche grüsse",
        "freundliche gruesse",
        "best regards",
        "kind regards",
        "regards",
    }


def _assert_no_unsupported_attachment_claim(body: str) -> None:
    """Reject body text that promises non-quotation files as attachments."""
    folded = (
        body.casefold()
        .replace("ü", "ue")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ß", "ss")
    )
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", folded)
    for sentence in sentences:
        if any(term in sentence for term in _EXTRA_DOCUMENT_TERMS) and any(
            term in sentence for term in _ATTACHMENT_CLAIM_TERMS
        ):
            raise RuntimeError(
                "LLM returned unsupported attachment claim for documents/certificates"
            )
        if any(term in sentence for term in ("zeichnung", "zeichnungen", "drawing", "drawings")) and any(
            term in sentence for term in _DRAWING_FOLLOW_UP_TERMS
        ):
            raise RuntimeError("LLM returned drawing follow-up wording")


def generate_reply_body(
    *,
    anfrage: Anfrage,
    quotation: Quotation,
    mail_body: str,
    style_hint: str,
    llm: LLMClient,
    acknowledged_requirements: list[Anforderung] | None = None,
    outgoing_attachment_names: list[str] | None = None,
    usage_callback: Callable[[TokenUsage], None] | None = None,
) -> tuple[str, Language]:
    """Run the LLM and return ``(body_text, language)``."""
    language = detect_language(mail_body)
    prompt = build_reply_body_prompt(
        anfrage,
        quotation,
        style_hint,
        language,
        acknowledged_requirements=acknowledged_requirements,
        outgoing_attachment_names=outgoing_attachment_names,
    )
    response = llm.generate(prompt=prompt)
    if response.usage is not None and usage_callback is not None:
        usage_callback(response.usage)
    body = _strip_response(response.text)
    if not body:
        raise RuntimeError("LLM returned empty reply body")
    _assert_no_unsupported_attachment_claim(body)
    return body, language
