import { useMemo } from "react";

import type { ReviewDetail } from "@/shared/api/reviews";

/**
 * Quality gate for the approval step.
 *
 * Two severities:
 *
 * - **blockers** prevent finalization. Examples: positions without a
 *   matched article AND without a manual price (i.e. price is zero
 *   guaranteed); empty mandatory customer fields. The approval button
 *   stays disabled until all blockers are cleared.
 *
 * - **warnings** are advisory. Examples: low overall match rate, lots
 *   of low-confidence positions, missing Beleg-Nr. The user can ignore
 *   them but should at least look once.
 *
 * Each issue carries a target area so the React UI can deep-link the
 * user straight to the right section in the combined request-data step.
 */

export type IssueStep = "positions" | "customer" | "approval";
export type IssueSeverity = "blocker" | "warning";

export interface Issue {
  id: string;
  severity: IssueSeverity;
  step: IssueStep;
  title: string;
  description: string;
}

export interface QualityGateResult {
  blockers: Issue[];
  warnings: Issue[];
  canApprove: boolean;
  stats: {
    totalPositions: number;
    unmatched: number;
    unmatchedWithoutPriceOverride: number;
    matchRate: number;
  };
}


export function useQualityGate(detail: ReviewDetail | undefined): QualityGateResult {
  return useMemo(() => evaluate(detail), [detail]);
}

function evaluate(detail: ReviewDetail | undefined): QualityGateResult {
  if (detail === undefined) {
    return {
      blockers: [],
      warnings: [],
      canApprove: false,
      stats: { totalPositions: 0, unmatched: 0, unmatchedWithoutPriceOverride: 0, matchRate: 1 },
    };
  }

  const blockers: Issue[] = [];
  const warnings: Issue[] = [];

  const totalPositions = detail?.anfrage.positionen.length ?? 0;
  const matches = detail?.matches ?? [];
  const overrides = detail?.manual_overrides ?? [];
  const acknowledgedRequirements = new Set(detail?.requirements_acknowledged ?? []);

  const overriddenPosNrs = new Set<number>(
    overrides
      .filter((o) => o.target === "pos")
      .map((o) => (o as { pos_nr: number }).pos_nr),
  );
  const overriddenArticles = new Set<string>(
    overrides
      .filter((o) => o.target === "artikel")
      .map((o) => (o as { artikel_nr: string }).artikel_nr),
  );

  const activePosNrs = new Set((detail?.anfrage.positionen ?? []).map((p) => p.pos_nr));
  const activeMatches = matches.filter((m) => activePosNrs.has(m.pos_nr));
  const unmatched = activeMatches.filter((m) => m.status === "no_match");
  const unmatchedWithoutPriceOverride = unmatched.filter((m) => {
    if (overriddenPosNrs.has(m.pos_nr)) return false;
    if (m.matched_artikelnr && overriddenArticles.has(m.matched_artikelnr)) {
      return false;
    }
    return true;
  });
  const unmatchedWithoutPriceOverridePosNrs = new Set(
    unmatchedWithoutPriceOverride.map((m) => m.pos_nr),
  );

  const matchedCount = activeMatches.filter((m) => m.status !== "no_match").length;
  const matchRate = totalPositions === 0 ? 1 : matchedCount / totalPositions;

  // ---------- Blockers ----------

  for (const m of unmatchedWithoutPriceOverride) {
    blockers.push({
      id: `unmatched:${m.pos_nr}`,
      severity: "blocker",
      step: "positions",
      title: `Pos ${m.pos_nr}: kein Stammdaten-Treffer`,
      description:
        "Bitte einen Artikel manuell zuordnen oder einen Stückpreis eintragen.",
    });
  }

  if (detail) {
    const a = detail.anfrage;
    if (!(a.kunde_firma ?? "").trim()) {
      blockers.push({
        id: "customer:firma",
        severity: "blocker",
        step: "customer",
        title: "Kundenfirma fehlt",
        description: "Pflichtfeld auf dem PDF-Header.",
      });
    }
    if (
      !(a.kunde_email ?? "").trim() &&
      !(a.kunde_ansprechpartner ?? "").trim()
    ) {
      blockers.push({
        id: "customer:contact",
        severity: "blocker",
        step: "customer",
        title: "Ansprechpartner oder E-Mail fehlt",
        description: "Mindestens eines der beiden Felder muss gesetzt sein.",
      });
    }
  }

  for (const item of detail?.quotation?.items ?? []) {
    if (unmatchedWithoutPriceOverridePosNrs.has(item.pos_nr)) continue;
    if (item.einzelpreis <= 0 || item.gesamtpreis <= 0) {
      blockers.push({
        id: `price:zero:${item.pos_nr}`,
        severity: "blocker",
        step: "positions",
        title: `Pos ${item.pos_nr}: Preis ist 0,00 EUR`,
        description: "Bitte Stückpreis und Gesamtpreis vor der Freigabe prüfen.",
      });
    }
  }

  const hasUnacknowledgedRequirements = (detail?.anfrage.anforderungen ?? []).some(
    (_requirement, idx) => !acknowledgedRequirements.has(idx),
  );
  if (hasUnacknowledgedRequirements) {
    blockers.push({
      id: "requirements:unacknowledged",
      severity: "blocker",
      step: "approval",
      title: "Angebotsanforderungen nicht vollständig bestätigt",
      description: "Bitte die Checkliste „Zu berücksichtigen im Angebot“ vollständig bestätigen.",
    });
  }

  const today = startOfToday();
  const pastDeliveries: Array<{ posNr: number; raw: string; parsed: Date }> = [];
  for (const pos of detail?.anfrage.positionen ?? []) {
    const deliveryDate = parseDateLike(pos.lieferzeit ?? "");
    if (deliveryDate && deliveryDate.getTime() < today.getTime()) {
      pastDeliveries.push({
        posNr: pos.pos_nr,
        raw: pos.lieferzeit ?? "",
        parsed: deliveryDate,
      });
    }
  }
  if (pastDeliveries.length > 0) {
    blockers.push({
      id: "delivery:past",
      severity: "blocker",
      step: "positions",
      title: deliveryTitle(pastDeliveries),
      description: `${deliverySummary(pastDeliveries)} Bitte Lieferzeiten aktualisieren oder entfernen.`,
    });
  }

  // ---------- Warnings ----------

  if (detail) {
    const a = detail.anfrage;
    if (!(a.belegnummer ?? "").trim()) {
      warnings.push({
        id: "belegnummer-missing",
        severity: "warning",
        step: "customer",
        title: "Belegnummer leer",
        description: "Ohne Belegnummer ist die Zuordnung im Backoffice mühsam.",
      });
    }
    if (!(a.kundennummer ?? "").trim()) {
      warnings.push({
        id: "kundennummer-missing",
        severity: "warning",
        step: "customer",
        title: "Kundennummer fehlt",
        description: "",
      });
    }
    if (!(a.datum ?? "").trim()) {
      warnings.push({
        id: "datum-missing",
        severity: "warning",
        step: "customer",
        title: "Anfragedatum fehlt",
        description: "",
      });
    }

    const email = (a.kunde_email ?? "").trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      warnings.push({
        id: "email-format",
        severity: "warning",
        step: "customer",
        title: "E-Mail-Adresse wirkt unvollständig",
        description: `"${email}" sieht nicht wie eine gültige Adresse aus.`,
      });
    }

    warnings.push(...commercialWarnings(a.incoterms, a.zahlungsbedingungen));
  }

  const priceWarningCount = detail?.quotation?.warnungen.length ?? 0;
  if (priceWarningCount > 0) {
    warnings.push({
      id: "price-warnings",
      severity: "warning",
      step: "positions",
      title: `${priceWarningCount} Preiswarnung(en) aus Kalkulation`,
      description: "Das Pricing hat Auffälligkeiten gemeldet (z.B. fehlende Listenpreise).",
    });
  }

  if (totalPositions >= 3 && matchRate < 0.5) {
    warnings.push({
      id: "low-match-rate",
      severity: "warning",
      step: "positions",
      title: `Niedrige Trefferquote (${Math.round(matchRate * 100)}%)`,
      description: "Weniger als die Hälfte der Positionen wurde sicher zugeordnet.",
    });
  }

  return {
    blockers,
    warnings,
    canApprove: blockers.length === 0,
    stats: {
      totalPositions,
      unmatched: unmatched.length,
      unmatchedWithoutPriceOverride: unmatchedWithoutPriceOverride.length,
      matchRate,
    },
  };
}

const INCOTERMS_2020 = new Set([
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
]);

function shorten(value: string, limit = 120): string {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`;
}

function deliveryTitle(deliveries: Array<{ posNr: number }>): string {
  if (deliveries.length === 1) {
    return `Pos ${deliveries[0].posNr}: Liefertermin liegt in der Vergangenheit`;
  }
  return `${deliveries.length} Positionen mit vergangenem Liefertermin`;
}

function deliverySummary(
  deliveries: Array<{ posNr: number; raw: string; parsed: Date }>,
): string {
  return shorten(
    `${deliveries
      .map((delivery) => `Pos ${delivery.posNr}: ${delivery.raw || formatIsoDate(delivery.parsed)}`)
      .join(", ")}.`,
  );
}

function startOfToday(): Date {
  const value = new Date();
  value.setHours(0, 0, 0, 0);
  return value;
}

function formatIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateLike(value: string): Date | null {
  const text = value.trim();
  if (!text) return null;

  const iso = /\b(\d{4})-(\d{1,2})-(\d{1,2})\b/.exec(text);
  if (iso) return safeDate(Number(iso[1]), Number(iso[2]), Number(iso[3]));

  const dotted = /\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b/.exec(text);
  if (dotted) {
    return safeDate(
      normaliseYear(Number(dotted[3])),
      Number(dotted[2]),
      Number(dotted[1]),
    );
  }

  const slashed = /\b(\d{1,2})\/(\d{1,2})\/(\d{2,4})\b/.exec(text);
  if (slashed) {
    return safeDate(
      normaliseYear(Number(slashed[3])),
      Number(slashed[2]),
      Number(slashed[1]),
    );
  }

  return null;
}

function normaliseYear(value: number): number {
  return value < 100 ? 2000 + value : value;
}

function safeDate(year: number, month: number, day: number): Date | null {
  const value = new Date(year, month - 1, day);
  if (
    value.getFullYear() !== year ||
    value.getMonth() !== month - 1 ||
    value.getDate() !== day
  ) {
    return null;
  }
  value.setHours(0, 0, 0, 0);
  return value;
}

function commercialWarnings(
  incoterms: string | null | undefined,
  paymentTerms: string | null | undefined,
): Issue[] {
  const warnings: Issue[] = [];
  const incotermsText = (incoterms ?? "").trim();
  const paymentText = (paymentTerms ?? "").trim();

  if (!incotermsText) {
    warnings.push({
      id: "incoterms-missing",
      severity: "warning",
      step: "customer",
      title: "Lieferbedingung / Incoterms fehlen",
      description: "Bitte vor Freigabe kaufmännisch ergänzen.",
    });
  } else {
    const code = extractIncotermCode(incotermsText);
    if (!code) {
      warnings.push({
        id: "incoterms-unknown",
        severity: "warning",
        step: "customer",
        title: "Lieferbedingung wirkt nicht wie ein Incoterm",
        description: `"${incotermsText}" konnte keinem Incoterms-2020-Code zugeordnet werden.`,
      });
    } else if (code === "DDP") {
      warnings.push({
        id: "incoterms-ddp",
        severity: "warning",
        step: "customer",
        title: "DDP erhöht Liefer- und Kostenpflichten",
        description: "Bitte bewusst prüfen, ob Zölle, Steuern und Lieferkosten kalkuliert sind.",
      });
    }
  }

  if (!paymentText) {
    warnings.push({
      id: "payment-terms-missing",
      severity: "warning",
      step: "customer",
      title: "Zahlungsbedingung fehlt",
      description: "Bitte vor Freigabe kaufmännisch ergänzen.",
    });
  } else {
    const maxDays = maxPaymentDays(paymentText);
    if (maxDays !== null && maxDays > 60) {
      warnings.push({
        id: "payment-long-term",
        severity: "warning",
        step: "customer",
        title: `Ungewöhnlich lange Zahlungsfrist (${maxDays} Tage)`,
        description: "Bitte Marge, Liquidität und Kundenkondition bewusst prüfen.",
      });
    }

    const discountPct = maxCashDiscountPct(paymentText);
    if (discountPct !== null && discountPct > 3) {
      warnings.push({
        id: "payment-high-discount",
        severity: "warning",
        step: "customer",
        title: `Ungewöhnlich hoher Skonto (${formatPercent(discountPct)} %)`,
        description: "Bitte prüfen, ob der Skonto in der Kalkulation berücksichtigt ist.",
      });
    }
  }

  return warnings;
}

function extractIncotermCode(value: string): string | null {
  for (const match of value.toUpperCase().matchAll(/\b[A-Z]{3}\b/g)) {
    const code = match[0];
    if (INCOTERMS_2020.has(code)) return code;
  }
  return null;
}

function maxPaymentDays(value: string): number | null {
  const matches = Array.from(value.matchAll(/\b(\d{1,3})\s*(?:tage|tag|days|day|d)\b/gi));
  if (matches.length === 0) return null;
  return Math.max(...matches.map((match) => Number(match[1])));
}

function maxCashDiscountPct(value: string): number | null {
  const lower = value.toLocaleLowerCase("de-DE");
  if (!lower.includes("skonto") && !lower.includes("discount")) return null;
  const matches = Array.from(value.matchAll(/(\d{1,2}(?:[,.]\d+)?)\s*%/g));
  if (matches.length === 0) return null;
  return Math.max(...matches.map((match) => Number(match[1].replace(",", "."))));
}

function formatPercent(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toLocaleString("de-DE");
}
