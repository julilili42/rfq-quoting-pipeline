"""LLM-generated cover-letter body for the Outlook reply.

Given the reviewed Anfrage + Quotation, produces a short complete plain-text
body in DE or EN. Used by the ``GET /reviews/{id}/reply-body`` endpoint when
the user enables the toggle on the /mail-vorlage page.
"""
from __future__ import annotations

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
) -> str:
    if not acknowledged:
        return ""
    if language == "de":
        header = (
            "\nVom Vertrieb bestätigte Sonderwünsche "
            "(bitte in einem Satz natürlich erwähnen, ohne Aufzählung):\n"
        )
    else:
        header = (
            "\nSpecial requests confirmed by Sales "
            "(weave naturally into one sentence, no bullet list):\n"
        )
    lines = [f"- {item.text}" for item in acknowledged]
    return header + "\n".join(lines) + "\n"


def build_reply_body_prompt(
    anfrage: Anfrage,
    quotation: Quotation,
    style_hint: str,
    language: Language,
    acknowledged_requirements: list[Anforderung] | None = None,
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
        acknowledged_requirements or [], language
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
            "- Schreibe 2 bis 4 kurze, natürlich klingende Sätze als Hauptteil.\n"
            "- Nimm konkret Bezug auf die Anfrage, ohne eine unnatürliche Artikelliste zu bauen.\n"
            "- Erwähne, dass das Angebot als PDF anhängt.\n"
            "- Nenne Lieferzeiten nur, wenn sie als Lieferzeit-Hinweis unten vorhanden sind.\n"
            "- Keine Marketing-Floskeln, keine Preisnennung im Fließtext.\n"
            "- Schließe mit 'Mit freundlichen Grüßen' und darunter '[Absender]'.\n"
            "- Plain Text mit Absatzumbrüchen; keine Aufzählungen, keine Überschriften, "
            "keine umschließenden Anführungszeichen.\n"
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
            "Positionen:\n"
            f"{positions_summary}\n"
            "\n"
            "Beispiel (anderer Fall):\n"
            "Sehr geehrte Damen und Herren,\n\n"
            "vielen Dank für Ihre Anfrage zu den drei Hydraulikpumpen. Anbei erhalten "
            "Sie unser Angebot als PDF. Sollten Sie zur angegebenen Lieferzeit "
            "Rückfragen haben, melden Sie sich gern.\n\n"
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
        "- Write 2 to 4 short, natural body sentences.\n"
        "- Reference the request specifically without turning the positions into a clumsy list.\n"
        "- Mention the attached PDF quotation.\n"
        "- Mention delivery times only if they are listed below.\n"
        "- No marketing fluff, no price mentions in the body.\n"
        "- Close with 'Best regards' followed by '[Absender]' on the next line.\n"
        "- Plain text with paragraph breaks; no bullet lists, no headings, no surrounding quotes.\n"
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
        "Positions:\n"
        f"{positions_summary}\n"
        "\n"
        "Example (different case):\n"
        "Dear Sir or Madam,\n\n"
        "Thank you for your inquiry regarding the three hydraulic pumps. Please find our "
        "quotation attached as a PDF. If you have any questions about the stated lead time, "
        "please do not hesitate to get in touch.\n\n"
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
    return cleaned.strip()


def generate_reply_body(
    *,
    anfrage: Anfrage,
    quotation: Quotation,
    mail_body: str,
    style_hint: str,
    llm: LLMClient,
    acknowledged_requirements: list[Anforderung] | None = None,
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
    )
    response = llm.generate(prompt=prompt)
    if response.usage is not None and usage_callback is not None:
        usage_callback(response.usage)
    body = _strip_response(response.text)
    if not body:
        raise RuntimeError("LLM returned empty reply body")
    return body, language
