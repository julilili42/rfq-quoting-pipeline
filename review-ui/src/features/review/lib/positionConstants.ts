import type { Position } from "@/shared/schemas/anfrage";
import type { MatchResult, MatchStatus } from "@/shared/schemas/matchResult";

export const VOLUME_TIERS = [
  { label: "< 100 Stk.", minQty: 0, rabatt: 0 },
  { label: "100–499", minQty: 100, rabatt: 5 },
  { label: "500–999", minQty: 500, rabatt: 10 },
  { label: "≥ 1.000", minQty: 1000, rabatt: 15 },
] as const;

export function activeTierIndex(qty: number): number {
  for (let i = VOLUME_TIERS.length - 1; i >= 0; i--) {
    if (qty >= VOLUME_TIERS[i].minQty) return i;
  }
  return 0;
}

export const CONFIDENCE_EXPLANATION =
  "KI-Selbsteinschätzung der Extraktion. Kein objektiver Prüfscore.";

export const ARTICLE_BADGE_TONE: Record<MatchStatus | "unknown", string> = {
  exact: "border-success/20 bg-success-soft text-success",
  fuzzy: "border-ek-blue/20 bg-ek-blue-soft text-ek-blue",
  semantic: "border-warning/20 bg-warning-soft text-warning",
  no_match: "border-brand/20 bg-brand-soft text-brand",
  unknown: "border-border bg-muted text-foreground",
};

export function displayArticleNumber(position: Position, match?: MatchResult): string {
  if (match?.status !== "no_match" && match?.matched_artikelnr) {
    return match.matched_artikelnr;
  }
  return position.artikelnummer || "Unbekannt";
}

export function articleBadgeTone(position: Position, match?: MatchResult): string {
  if (match?.status !== "no_match" && match?.matched_artikelnr) {
    return ARTICLE_BADGE_TONE[match.status];
  }
  return position.artikelnummer ? ARTICLE_BADGE_TONE.no_match : ARTICLE_BADGE_TONE.unknown;
}
