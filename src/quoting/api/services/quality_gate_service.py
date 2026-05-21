"""Server-side approval quality gate.

The React UI has a client-side quality gate for ergonomics, but the
finalize endpoint must enforce the same class of checks before it writes
a final PDF and marks the review approved.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.pricing import Quotation

IssueSeverity = Literal["blocker", "warning"]
IssueStep = Literal["positions", "customer", "approval"]

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_INCOTERMS_2020 = {
    "EXW",
    "FCA",
    "CPT",
    "CIP",
    "DAP",
    "DPU",
    "DDP",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
}


@dataclass(frozen=True)
class QualityIssue:
    id: str
    severity: IssueSeverity
    step: IssueStep
    title: str
    description: str = ""


@dataclass(frozen=True)
class QualityGateResult:
    blockers: list[QualityIssue]
    warnings: list[QualityIssue]
    stats: dict[str, int | float]

    @property
    def can_approve(self) -> bool:
        return len(self.blockers) == 0

    @property
    def requires_acknowledgement(self) -> bool:
        return bool(self.blockers or self.warnings)

    def to_dict(self) -> dict:
        return {
            "blockers": [asdict(issue) for issue in self.blockers],
            "warnings": [asdict(issue) for issue in self.warnings],
            "canApprove": self.can_approve,
            "stats": self.stats,
        }


def evaluate_quality_gate(
    anfrage: Anfrage,
    matches: list[MatchResult],
    quotation: Quotation | None,
    overrides: list[dict] | None = None,
    acknowledged_requirement_indices: list[int] | None = None,
    *,
    today: date | None = None,
) -> QualityGateResult:
    blockers: list[QualityIssue] = []
    warnings: list[QualityIssue] = []
    overrides = overrides or []
    today = today or date.today()

    positions = list(anfrage.positionen)
    total_positions = len(positions)
    active_pos_nrs = {pos.pos_nr for pos in positions}
    active_matches = [match for match in matches if match.pos_nr in active_pos_nrs]

    price_override_pos_nrs = _price_override_pos_nrs(overrides)
    price_override_articles = _price_override_articles(overrides)

    unmatched = [match for match in active_matches if match.status == "no_match"]
    unmatched_without_price_override = [
        match
        for match in unmatched
        if not _has_price_override(match, price_override_pos_nrs, price_override_articles)
    ]
    unmatched_blocker_pos_nrs = {match.pos_nr for match in unmatched_without_price_override}

    matched_count = len([match for match in active_matches if match.status != "no_match"])
    match_rate = 1.0 if total_positions == 0 else matched_count / total_positions

    for match in unmatched_without_price_override:
        blockers.append(
            QualityIssue(
                id=f"unmatched:{match.pos_nr}",
                severity="blocker",
                step="positions",
                title=f"Pos {match.pos_nr}: kein Stammdaten-Treffer",
                description=(
                    "Bitte einen Artikel manuell zuordnen oder einen Stückpreis eintragen."
                ),
            )
        )

    if not _text(anfrage.kunde_firma):
        blockers.append(
            QualityIssue(
                id="customer:firma",
                severity="blocker",
                step="customer",
                title="Kundenfirma fehlt",
                description="Pflichtfeld auf dem PDF-Header.",
            )
        )

    if not _text(anfrage.kunde_email) and not _text(anfrage.kunde_ansprechpartner):
        blockers.append(
            QualityIssue(
                id="customer:contact",
                severity="blocker",
                step="customer",
                title="Ansprechpartner oder E-Mail fehlt",
                description="Mindestens eines der beiden Felder muss gesetzt sein.",
            )
        )

    if quotation is not None:
        for item in quotation.items:
            if item.pos_nr in unmatched_blocker_pos_nrs:
                continue
            if item.einzelpreis <= 0 or item.gesamtpreis <= 0:
                blockers.append(
                    QualityIssue(
                        id=f"price:zero:{item.pos_nr}",
                        severity="blocker",
                        step="positions",
                        title=f"Pos {item.pos_nr}: Preis ist 0,00 EUR",
                        description="Bitte Stückpreis und Gesamtpreis vor der Freigabe prüfen.",
                    )
                )

    unacknowledged_requirements = _unacknowledged_requirements(
        anfrage,
        acknowledged_requirement_indices,
    )
    if unacknowledged_requirements:
        blockers.append(
            QualityIssue(
                id="requirements:unacknowledged",
                severity="blocker",
                step="approval",
                title="Angebotsanforderungen nicht vollständig bestätigt",
                description=(
                    "Bitte die Checkliste 'Zu berücksichtigen im Angebot' "
                    "vollständig bestätigen."
                ),
            )
        )

    past_deliveries: list[tuple[int, str, date]] = []
    for pos in positions:
        delivery_date = _parse_date_like(pos.lieferzeit or "")
        if delivery_date is not None and delivery_date < today:
            past_deliveries.append((pos.pos_nr, pos.lieferzeit or "", delivery_date))

    if past_deliveries:
        blockers.append(
            QualityIssue(
                id="delivery:past",
                severity="blocker",
                step="positions",
                title=_delivery_title(past_deliveries),
                description=(
                    f"{_delivery_summary(past_deliveries)} Bitte Lieferzeiten "
                    "aktualisieren oder entfernen."
                ),
            )
        )

    if not _text(anfrage.belegnummer):
        warnings.append(
            QualityIssue(
                id="belegnummer-missing",
                severity="warning",
                step="customer",
                title="Belegnummer leer",
                description="Ohne Belegnummer ist die Zuordnung im Backoffice mühsam.",
            )
        )

    if not _text(anfrage.kundennummer):
        warnings.append(
            QualityIssue(
                id="kundennummer-missing",
                severity="warning",
                step="customer",
                title="Kundennummer fehlt",
            )
        )

    if not _text(anfrage.datum):
        warnings.append(
            QualityIssue(
                id="datum-missing",
                severity="warning",
                step="customer",
                title="Anfragedatum fehlt",
            )
        )

    email = _text(anfrage.kunde_email)
    if email and not _EMAIL_RE.match(email):
        warnings.append(
            QualityIssue(
                id="email-format",
                severity="warning",
                step="customer",
                title="E-Mail-Adresse wirkt unvollständig",
                description=f'"{email}" sieht nicht wie eine gültige Adresse aus.',
            )
        )

    warnings.extend(_commercial_warnings(anfrage.incoterms, anfrage.zahlungsbedingungen))

    price_warning_count = len(quotation.warnungen) if quotation is not None else 0
    if price_warning_count > 0:
        warnings.append(
            QualityIssue(
                id="price-warnings",
                severity="warning",
                step="positions",
                title=f"{price_warning_count} Preiswarnung(en) aus Kalkulation",
                description="Das Pricing hat Auffälligkeiten gemeldet.",
            )
        )

    if total_positions >= 3 and match_rate < 0.5:
        warnings.append(
            QualityIssue(
                id="low-match-rate",
                severity="warning",
                step="positions",
                title=f"Niedrige Trefferquote ({round(match_rate * 100)}%)",
                description="Weniger als die Hälfte der Positionen wurde sicher zugeordnet.",
            )
        )

    return QualityGateResult(
        blockers=blockers,
        warnings=warnings,
        stats={
            "totalPositions": total_positions,
            "unmatched": len(unmatched),
            "unmatchedWithoutPriceOverride": len(unmatched_without_price_override),
            "matchRate": match_rate,
        },
    )


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _unacknowledged_requirements(
    anfrage: Anfrage,
    acknowledged_requirement_indices: list[int] | None,
) -> list[int]:
    acknowledged = {
        idx for idx in (acknowledged_requirement_indices or []) if idx >= 0
    }
    return [
        idx
        for idx, _requirement in enumerate(anfrage.anforderungen)
        if idx not in acknowledged
    ]


def _delivery_title(past_deliveries: list[tuple[int, str, date]]) -> str:
    count = len(past_deliveries)
    if count == 1:
        return f"Pos {past_deliveries[0][0]}: Liefertermin liegt in der Vergangenheit"
    return f"{count} Positionen mit vergangenem Liefertermin"


def _delivery_summary(past_deliveries: list[tuple[int, str, date]]) -> str:
    details = ", ".join(
        f"Pos {pos_nr}: {raw or parsed.isoformat()}"
        for pos_nr, raw, parsed in past_deliveries
    )
    return _shorten(f"{details}.")


def _shorten(value: str, *, limit: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _parse_date_like(value: str) -> date | None:
    text = _text(value)
    if not text:
        return None

    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        return _safe_date(
            int(iso_match.group(1)),
            int(iso_match.group(2)),
            int(iso_match.group(3)),
        )

    dot_match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", text)
    if dot_match:
        return _safe_date(
            _normalise_year(int(dot_match.group(3))),
            int(dot_match.group(2)),
            int(dot_match.group(1)),
        )

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text)
    if slash_match:
        return _safe_date(
            _normalise_year(int(slash_match.group(3))),
            int(slash_match.group(2)),
            int(slash_match.group(1)),
        )

    return None


def _normalise_year(value: int) -> int:
    if value < 100:
        return 2000 + value
    return value


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _commercial_warnings(
    incoterms: str | None,
    payment_terms: str | None,
) -> list[QualityIssue]:
    warnings: list[QualityIssue] = []
    incoterms_text = _text(incoterms)
    payment_text = _text(payment_terms)

    if not incoterms_text:
        warnings.append(
            QualityIssue(
                id="incoterms-missing",
                severity="warning",
                step="customer",
                title="Lieferbedingung / Incoterms fehlen",
                description="Bitte vor Freigabe kaufmännisch ergänzen.",
            )
        )
    else:
        code = _extract_incoterm_code(incoterms_text)
        if code is None:
            warnings.append(
                QualityIssue(
                    id="incoterms-unknown",
                    severity="warning",
                    step="customer",
                    title="Lieferbedingung wirkt nicht wie ein Incoterm",
                    description=f"'{incoterms_text}' konnte keinem Incoterms-2020-Code zugeordnet werden.",
                )
            )
        elif code == "DDP":
            warnings.append(
                QualityIssue(
                    id="incoterms-ddp",
                    severity="warning",
                    step="customer",
                    title="DDP erhöht Liefer- und Kostenpflichten",
                    description="Bitte bewusst prüfen, ob Zölle, Steuern und Lieferkosten kalkuliert sind.",
                )
            )

    if not payment_text:
        warnings.append(
            QualityIssue(
                id="payment-terms-missing",
                severity="warning",
                step="customer",
                title="Zahlungsbedingung fehlt",
                description="Bitte vor Freigabe kaufmännisch ergänzen.",
            )
        )
    else:
        max_days = _max_payment_days(payment_text)
        if max_days is not None and max_days > 60:
            warnings.append(
                QualityIssue(
                    id="payment-long-term",
                    severity="warning",
                    step="customer",
                    title=f"Ungewöhnlich lange Zahlungsfrist ({max_days} Tage)",
                    description="Bitte Marge, Liquidität und Kundenkondition bewusst prüfen.",
                )
            )
        discount_pct = _max_cash_discount_pct(payment_text)
        if discount_pct is not None and discount_pct > 3:
            warnings.append(
                QualityIssue(
                    id="payment-high-discount",
                    severity="warning",
                    step="customer",
                    title=f"Ungewöhnlich hoher Skonto ({discount_pct:g} %)",
                    description="Bitte prüfen, ob der Skonto in der Kalkulation berücksichtigt ist.",
                )
            )

    return warnings


def _extract_incoterm_code(value: str) -> str | None:
    text = value.upper()
    for match in re.finditer(r"\b[A-Z]{3}\b", text):
        code = match.group(0)
        if code in _INCOTERMS_2020:
            return code
    return None


def _max_payment_days(value: str) -> int | None:
    matches = re.findall(r"\b(\d{1,3})\s*(?:tage|tag|days|day|d)\b", value, re.I)
    if not matches:
        return None
    return max(int(match) for match in matches)


def _max_cash_discount_pct(value: str) -> float | None:
    if "skonto" not in value.casefold() and "discount" not in value.casefold():
        return None
    matches = re.findall(r"(\d{1,2}(?:[,.]\d+)?)\s*%", value)
    if not matches:
        return None
    return max(float(match.replace(",", ".")) for match in matches)


def _price_override_pos_nrs(overrides: list[dict]) -> set[int]:
    result: set[int] = set()
    for override in overrides:
        if not isinstance(override, dict):
            continue
        if override.get("target") != "pos":
            continue
        if override.get("mode") not in {"unit_price_eur", "total_price_eur"}:
            continue
        try:
            result.add(int(override.get("pos_nr") or 0))
        except (TypeError, ValueError):
            continue
    return result


def _price_override_articles(overrides: list[dict]) -> set[str]:
    result: set[str] = set()
    for override in overrides:
        if not isinstance(override, dict):
            continue
        if override.get("target") != "artikel":
            continue
        if override.get("mode") not in {"unit_price_eur", "total_price_eur"}:
            continue
        article = _text(override.get("artikel_nr"))
        if article:
            result.add(article)
    return result


def _has_price_override(
    match: MatchResult,
    price_override_pos_nrs: set[int],
    price_override_articles: set[str],
) -> bool:
    if match.pos_nr in price_override_pos_nrs:
        return True
    return bool(match.matched_artikelnr and match.matched_artikelnr in price_override_articles)
