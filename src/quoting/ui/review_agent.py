"""Helpers for the review chat-agent in Streamlit UI."""
from __future__ import annotations

import re
from dataclasses import asdict

from ..matching import MatchResult
from ..pricing import Quotation, apply_manual_overrides, upsert_override

__all__ = [
    "apply_manual_overrides",
    "build_agent_summary",
    "build_general_agent_reply",
    "detect_agent_language",
    "parse_discount_instruction",
    "parse_edit_instruction",
    "quotation_to_state",
    "upsert_override",
]

_DISCOUNT_KEYWORDS = ("discount", "rabatt")
_PRICE_KEYWORDS = ("euro", "eur", "preis", "price", "set", "mach", "mache")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _normalize_for_parsing(text: str) -> str:
    normalized = (text or "").strip().lower().replace("\u20ac", " euro ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\b(pos|position)(\d+)\b", r"\1 \2", normalized)
    normalized = re.sub(r"\b(artikel|article|product)([a-z0-9._\-/]+)\b", r"\1 \2", normalized)
    return normalized


def detect_agent_language(email_text: str, fallback_text: str = "") -> str:
    """Detect preferred agent language from email text.

    Returns language code: "de" or "en".
    """
    sample = f"{email_text or ''} {fallback_text or ''}".strip()
    if not sample:
        return "de"

    if _CYRILLIC_RE.search(sample):
        return "en"

    lower = sample.lower()
    de_hits = sum(
        lower.count(w)
        for w in (
            " und ", " der ", " die ", " das ", " mit ", " fuer ", " für ",
            "anfrage", "angebot", "lieferzeit", "menge", "artikel",
        )
    )
    en_hits = sum(
        lower.count(w)
        for w in (
            " and ", " the ", " with ", "request", "quotation",
            "delivery", "quantity", "discount", "product",
        )
    )
    return "de" if de_hits >= en_hits else "en"


def _t(lang: str, key: str) -> str:
    de = {
        "discount_missing_pct": "Bitte gib den Rabatt in Prozent an, z. B. 7%.",
        "accepted_pos": "Verstanden: Rabatt {pct:.1f}% fuer Position {target}.",
        "accepted_art": "Verstanden: Rabatt {pct:.1f}% fuer Artikel {target}.",
        "accepted_pos_price": "Verstanden: Position {target} auf {price:.2f} EUR gesetzt.",
        "accepted_art_price": "Verstanden: Artikel {target} auf {price:.2f} EUR gesetzt.",
        "accepted_pos_total": "Verstanden: Gesamtpreis fuer Position {target} auf {price:.2f} EUR gesetzt.",
        "accepted_art_total": "Verstanden: Gesamtpreis fuer Artikel {target} auf {price:.2f} EUR gesetzt.",
        "discount_target_missing": "Kein Rabattziel erkannt. Bitte Artikel oder Position angeben (z. B. pos 2).",
        "price_target_missing": "Kein Preisziel erkannt. Bitte Artikel oder Position angeben (z. B. pos 3 = 10 EUR).",
        "price_missing_value": "Bitte gib einen Betrag in EUR an, z. B. 10 EUR.",
        "summary_done": "Fertig. Der Angebotsentwurf wurde erstellt.",
        "summary_total": "Gesamtsumme: {total:.2f} {currency}.",
        "summary_matching": "Matching: exact={exact}, fuzzy={fuzzy}, semantic={semantic}, no_match={no_match}.",
        "summary_manual_yes": "Manuelle Anpassungen: {count}.",
        "summary_manual_no": "Noch keine manuellen Anpassungen angewendet.",
        "summary_top": "Wichtigste Preispositionen:",
        "summary_no_positions": "- Keine Positionen",
        "summary_example_header": "Du kannst z. B. folgende Anpassung anfordern:",
        "summary_example_1": "- Gib 7% Rabatt auf Artikel 001GLP108015",
        "summary_example_2": "- Setze pos 3 auf 10 EUR",
        "reply_total": "Aktuelle Gesamtsumme: {total:.2f} {currency}.",
        "reply_no_warnings": "Keine kritischen Warnungen vorhanden.",
        "reply_warnings_header": "Warnungen:",
        "reply_help": "Ich kann kaufmaennische Anpassungen anwenden und das PDF direkt neu berechnen. Beispiele: 'Gib 5% Rabatt auf Artikel ...' oder 'Setze pos 3 auf 10 EUR'.",
    }
    en = {
        "discount_missing_pct": "Please provide a discount percentage, e.g. 7%.",
        "accepted_pos": "Applied: {pct:.1f}% discount for position {target}.",
        "accepted_art": "Applied: {pct:.1f}% discount for article {target}.",
        "accepted_pos_price": "Applied: position {target} unit price set to {price:.2f} EUR.",
        "accepted_art_price": "Applied: article {target} unit price set to {price:.2f} EUR.",
        "accepted_pos_total": "Applied: total price for position {target} set to {price:.2f} EUR.",
        "accepted_art_total": "Applied: total price for article {target} set to {price:.2f} EUR.",
        "discount_target_missing": "I could not identify the discount target. Please specify article or position (e.g. pos 2).",
        "price_target_missing": "I could not identify the price target. Please specify article or position (e.g. pos 3 = 10 EUR).",
        "price_missing_value": "Please provide an amount in EUR, e.g. 10 EUR.",
        "summary_done": "Done. Draft quotation has been prepared.",
        "summary_total": "Total amount: {total:.2f} {currency}.",
        "summary_matching": "Matching: exact={exact}, fuzzy={fuzzy}, semantic={semantic}, no_match={no_match}.",
        "summary_manual_yes": "Manual adjustments applied: {count}.",
        "summary_manual_no": "No manual adjustments applied yet.",
        "summary_top": "Top price positions:",
        "summary_no_positions": "- No positions",
        "summary_example_header": "You can ask me to apply an edit, for example:",
        "summary_example_1": "- Apply 7% discount on article 001GLP108015",
        "summary_example_2": "- Set pos 3 to 10 EUR",
        "reply_total": "Current total amount: {total:.2f} {currency}.",
        "reply_no_warnings": "No critical warnings.",
        "reply_warnings_header": "Warnings:",
        "reply_help": "I can apply commercial edits and immediately regenerate the PDF. Examples: 'Apply 5% discount on article ...' or 'Set pos 3 to 10 EUR'.",
    }
    table = {"de": de, "en": en}.get(lang, de)
    return table[key]


def parse_discount_instruction(
    message: str,
    known_article_numbers: list[str],
    lang: str = "de",
) -> tuple[dict | None, str]:
    """Parse manual discount command from free-text message.

    Supported examples:
    - "Сделай скидку 10% на артикул 001GLP108015"
    - "discount 5% for pos 2"
    """
    text = (message or "").strip()
    text_l = text.lower()

    if not any(k in text_l for k in _DISCOUNT_KEYWORDS):
        return None, ""

    pct_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*%", text_l)
    if not pct_match:
        return None, _t(lang, "discount_missing_pct")

    pct = float(pct_match.group(1).replace(",", "."))
    pct = max(0.0, min(100.0, pct))

    pos_match = re.search(r"(?:pos(?:ition)?)\s*[#: ]?\s*(\d+)", text_l)
    if pos_match:
        return {
            "target": "pos",
            "pos_nr": int(pos_match.group(1)),
            "discount_pct": pct,
        }, _t(lang, "accepted_pos").format(pct=pct, target=int(pos_match.group(1)))

    art_match = re.search(
        r"(?:artikel(?:nummer)?|art(?:ikel)?(?:\.|ikel)?\s*nr|product)\s*[#: ]?\s*([a-z0-9._\-/]+)",
        text_l,
    )
    if art_match:
        artikel = art_match.group(1).upper()
        return {
            "target": "artikel",
            "artikel_nr": artikel,
            "discount_pct": pct,
        }, _t(lang, "accepted_art").format(pct=pct, target=artikel)

    # Fallback: try to find known article number directly in message
    upper_text = text.upper()
    for artikel in known_article_numbers:
        if artikel and artikel in upper_text:
            return {
                "target": "artikel",
                "artikel_nr": artikel,
                "discount_pct": pct,
            }, _t(lang, "accepted_art").format(pct=pct, target=artikel)

    return None, _t(lang, "discount_target_missing")


def parse_edit_instruction(
    message: str,
    known_article_numbers: list[str],
    lang: str = "de",
) -> tuple[dict | None, str]:
    """Parse flexible commercial edits (discount % or fixed EUR unit price)."""
    text = (message or "").strip()
    text_l = _normalize_for_parsing(text)

    pos_match = re.search(r"(?:pos(?:ition)?)\s*[#: ]?\s*(\d+)", text_l)
    art_match = re.search(
        r"(?:artikel(?:nummer)?|art(?:ikel)?(?:\.|ikel)?\s*nr|product)\s*[#: ]?\s*([a-z0-9._\-/]+)",
        text_l,
    )
    target: dict | None = None
    if pos_match:
        target = {"target": "pos", "pos_nr": int(pos_match.group(1))}
    elif art_match:
        target = {"target": "artikel", "artikel_nr": art_match.group(1).upper()}
    else:
        upper_text = text.upper()
        for artikel in known_article_numbers:
            if artikel and artikel in upper_text:
                target = {"target": "artikel", "artikel_nr": artikel}
                break

    pct_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*%", text_l)
    if pct_match and not target and any(k in text_l for k in _DISCOUNT_KEYWORDS):
        return None, _t(lang, "discount_target_missing")
    if pct_match and target:
        pct = float(pct_match.group(1).replace(",", "."))
        pct = max(0.0, min(100.0, pct))
        if target["target"] == "pos":
            return {
                **target,
                "mode": "discount_pct",
                "discount_pct": pct,
            }, _t(lang, "accepted_pos").format(pct=pct, target=target["pos_nr"])
        return {
            **target,
            "mode": "discount_pct",
            "discount_pct": pct,
        }, _t(lang, "accepted_art").format(pct=pct, target=target["artikel_nr"])

    # Fixed price in EUR: accepts "10 euro", "10 eur", "10€", "€10", "= 10", "auf 10"
    eur_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:€|eur|euro)\b", text_l)
    if not eur_match:
        eur_match = re.search(r"(?:€|eur|euro)\s*(\d+(?:[\.,]\d+)?)\b", text_l)
    if not eur_match:
        eur_match = re.search(r"(?:=|auf|to|at)\s*(\d+(?:[\.,]\d+)?)\b", text_l)

    has_price_intent = any(k in text_l for k in _PRICE_KEYWORDS)
    total_intent = any(k in text_l for k in ("gesamt", "total", "sum", "summe"))
    if eur_match and target and has_price_intent:
        price = float(eur_match.group(1).replace(",", "."))
        price = max(0.0, price)

        if total_intent:
            if target["target"] == "pos":
                return {
                    **target,
                    "mode": "total_price_eur",
                    "total_price_eur": price,
                }, _t(lang, "accepted_pos_total").format(price=price, target=target["pos_nr"])
            return {
                **target,
                "mode": "total_price_eur",
                "total_price_eur": price,
            }, _t(lang, "accepted_art_total").format(price=price, target=target["artikel_nr"])

        if target["target"] == "pos":
            return {
                **target,
                "mode": "unit_price_eur",
                "unit_price_eur": price,
            }, _t(lang, "accepted_pos_price").format(price=price, target=target["pos_nr"])
        return {
            **target,
            "mode": "unit_price_eur",
            "unit_price_eur": price,
        }, _t(lang, "accepted_art_price").format(price=price, target=target["artikel_nr"])

    if target and has_price_intent:
        return None, _t(lang, "price_missing_value")
    if eur_match and not target:
        return None, _t(lang, "price_target_missing")

    return None, ""


def build_agent_summary(
    quotation: Quotation,
    matches: list[MatchResult],
    applied_items: int = 0,
    lang: str = "de",
) -> str:
    """Build concise first assistant message with key commercial points."""
    exact = sum(1 for m in matches if m.status == "exact")
    fuzzy = sum(1 for m in matches if m.status == "fuzzy")
    semantic = sum(1 for m in matches if m.status == "semantic")
    no_match = sum(1 for m in matches if m.status == "no_match")

    top_items = sorted(quotation.items, key=lambda it: it.gesamtpreis, reverse=True)[:3]
    top_lines = "\n".join(
        f"- Pos {it.pos_nr}: {it.artikel_nr} -> {it.gesamtpreis:.2f} EUR"
        for it in top_items
    ) or _t(lang, "summary_no_positions")

    manual_line = (
        _t(lang, "summary_manual_yes").format(count=applied_items)
        if applied_items
        else _t(lang, "summary_manual_no")
    )

    return (
        f"{_t(lang, 'summary_done')}\n\n"
        f"{_t(lang, 'summary_total').format(total=quotation.gesamtsumme, currency=quotation.waehrung)}\n"
        f"{_t(lang, 'summary_matching').format(exact=exact, fuzzy=fuzzy, semantic=semantic, no_match=no_match)}\n"
        f"{manual_line}\n\n"
        f"{_t(lang, 'summary_top')}\n"
        f"{top_lines}\n\n"
        f"{_t(lang, 'summary_example_header')}\n"
        f"{_t(lang, 'summary_example_1')}\n"
        f"{_t(lang, 'summary_example_2')}"
    )


def build_general_agent_reply(message: str, quotation: Quotation, lang: str = "de") -> str:
    """Fallback response when command is not recognized."""
    text = message.strip().lower()
    if any(k in text for k in ("total", "sum", "gesamt")):
        return _t(lang, "reply_total").format(total=quotation.gesamtsumme, currency=quotation.waehrung)
    if any(k in text for k in ("warning", "warn", "risiko", "risk")):
        if not quotation.warnungen:
            return _t(lang, "reply_no_warnings")
        return _t(lang, "reply_warnings_header") + "\n" + "\n".join(f"- {w}" for w in quotation.warnungen)

    return _t(lang, "reply_help")


def quotation_to_state(quotation: Quotation) -> dict:
    """Serialize dataclass quotation for Streamlit session state."""
    return asdict(quotation)
