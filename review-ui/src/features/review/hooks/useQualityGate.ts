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
 * Each issue carries a `step` so the React UI can deep-link the user
 * straight to the right editor.
 */

export type IssueStep = "positions" | "customer";
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
  /** Compact stat strip: "X von Y Positionen ohne Match" etc. */
  stats: {
    totalPositions: number;
    unmatched: number;
    unmatchedWithoutPriceOverride: number;
    lowConfidence: number;
    matchRate: number;
  };
}

/* Tunables — kept here so policy changes are one-line edits. */
const LOW_MATCH_RATE_THRESHOLD = 0.7;
const LOW_CONFIDENCE_RATIO_THRESHOLD = 0.3;

export function useQualityGate(detail: ReviewDetail | undefined): QualityGateResult {
  return useMemo(() => evaluate(detail), [detail]);
}

function evaluate(detail: ReviewDetail | undefined): QualityGateResult {
  if (detail === undefined) {
    return {
      blockers: [],
      warnings: [],
      canApprove: false,
      stats: { totalPositions: 0, unmatched: 0, unmatchedWithoutPriceOverride: 0, lowConfidence: 0, matchRate: 1 },
    };
  }

  const blockers: Issue[] = [];
  const warnings: Issue[] = [];

  const totalPositions = detail?.anfrage.positionen.length ?? 0;
  const matches = detail?.matches ?? [];
  const overrides = detail?.manual_overrides ?? [];

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

  const lowConfidence = (detail?.anfrage.positionen ?? []).filter(
    (p) => p.confidence === "low",
  ).length;

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

  // ---------- Warnings ----------

  if (totalPositions > 0 && matchRate < LOW_MATCH_RATE_THRESHOLD) {
    warnings.push({
      id: "match-rate-low",
      severity: "warning",
      step: "positions",
      title: `Match-Quote nur ${Math.round(matchRate * 100)}%`,
      description: "",
    });
  }

  if (
    totalPositions > 0 &&
    lowConfidence / totalPositions > LOW_CONFIDENCE_RATIO_THRESHOLD
  ) {
    warnings.push({
      id: "low-confidence",
      severity: "warning",
      step: "positions",
      title: `${lowConfidence} Position(en) mit geringer KI-Sicherheit`,
      description: "",
    });
  }

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
    if (!(a.vorgangsnummer ?? "").trim()) {
      warnings.push({
        id: "vorgangsnummer-missing",
        severity: "warning",
        step: "customer",
        title: "Vorgangsnummer fehlt",
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
  }

  return {
    blockers,
    warnings,
    canApprove: blockers.length === 0,
    stats: {
      totalPositions,
      unmatched: unmatched.length,
      unmatchedWithoutPriceOverride: unmatchedWithoutPriceOverride.length,
      lowConfidence,
      matchRate,
    },
  };
}
