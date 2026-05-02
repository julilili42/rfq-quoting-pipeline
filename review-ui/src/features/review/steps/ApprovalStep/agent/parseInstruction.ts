import type { ManualOverride } from "@/shared/schemas/quotation";

import type { AgentLang } from "./i18n";
import { t } from "./i18n";

/**
 * Free-text → ManualOverride parser.
 *
 * Direct port of `quoting/ui/review_agent.parse_edit_instruction`.
 * Recognises these patterns (case-insensitive):
 *
 *   "discount 5% pos 2"             → discount_pct on pos 2
 *   "5% Rabatt auf Artikel ABC"     → discount_pct on article ABC
 *   "Setze pos 3 auf 10 EUR"        → unit_price_eur on pos 3
 *   "Pos 4 = 12 EUR"                → unit_price_eur on pos 4
 *   "Gesamtpreis pos 5 200 EUR"     → total_price_eur on pos 5
 *
 * Returns a `{ override, feedback }` pair. Either piece may be empty —
 * a non-empty `feedback` without an `override` is a hint to the user
 * (e.g. "you mentioned a discount but no target").
 */

interface ParseResult {
  override: ManualOverride | null;
  feedback: string;
}

const DISCOUNT_KEYWORDS = ["discount", "rabatt"];
const PRICE_KEYWORDS = ["euro", "eur", "preis", "price", "set", "mach", "mache"];
const TOTAL_KEYWORDS = ["gesamt", "total", "sum", "summe"];

function normalize(text: string): string {
  let out = (text ?? "").trim().toLowerCase().replaceAll("\u20ac", " euro ");
  out = out.replaceAll(/\s+/g, " ");
  out = out.replaceAll(/\b(pos|position)(\d+)\b/g, "$1 $2");
  out = out.replaceAll(/\b(artikel|article|product)([a-z0-9._\-/]+)\b/g, "$1 $2");
  return out;
}

function findTarget(
  text: string,
  textLower: string,
  knownArticles: string[],
):
  | { kind: "pos"; pos_nr: number; display: string }
  | { kind: "artikel"; artikel_nr: string; display: string }
  | null {
  const posMatch = textLower.match(/(?:pos(?:ition)?)\s*[#: ]?\s*(\d+)/);
  if (posMatch) {
    const num = parseInt(posMatch[1], 10);
    return { kind: "pos", pos_nr: num, display: String(num) };
  }

  const artMatch = textLower.match(
    /(?:artikel(?:nummer)?|art(?:ikel)?(?:\.|ikel)?\s*nr|product)\s*[#: ]?\s*([a-z0-9._\-/]+)/,
  );
  if (artMatch) {
    const art = artMatch[1].toUpperCase();
    return { kind: "artikel", artikel_nr: art, display: art };
  }

  // Fallback: scan the original (unlowered) text for any known article number.
  const upperText = text.toUpperCase();
  for (const art of knownArticles) {
    if (art && upperText.includes(art)) {
      return { kind: "artikel", artikel_nr: art, display: art };
    }
  }
  return null;
}

export function parseEditInstruction(
  message: string,
  knownArticles: string[],
  lang: AgentLang = "de",
): ParseResult {
  const text = (message ?? "").trim();
  if (!text) return { override: null, feedback: "" };
  const textLower = normalize(text);

  const target = findTarget(text, textLower, knownArticles);
  const containsDiscountWord = DISCOUNT_KEYWORDS.some((k) => textLower.includes(k));
  const containsPriceWord = PRICE_KEYWORDS.some((k) => textLower.includes(k));
  const containsTotalWord = TOTAL_KEYWORDS.some((k) => textLower.includes(k));

  // ----- discount in % -----
  const pctMatch = textLower.match(/(\d+(?:[.,]\d+)?)\s*%/);
  if (pctMatch && !target && containsDiscountWord) {
    return { override: null, feedback: t(lang, "discount_target_missing") };
  }
  if (pctMatch && target) {
    const pct = clamp(parseFloat(pctMatch[1].replace(",", ".")), 0, 100);
    if (target.kind === "pos") {
      return {
        override: {
          target: "pos",
          pos_nr: target.pos_nr,
          mode: "discount_pct",
          discount_pct: pct,
        },
        feedback: t(lang, "accepted_pos", { pct: pct.toFixed(1), target: target.display }),
      };
    }
    return {
      override: {
        target: "artikel",
        artikel_nr: target.artikel_nr,
        mode: "discount_pct",
        discount_pct: pct,
      },
      feedback: t(lang, "accepted_art", { pct: pct.toFixed(1), target: target.display }),
    };
  }

  // ----- fixed EUR amount -----
  const eurMatch =
    textLower.match(/(\d+(?:[.,]\d+)?)\s*(?:eur|euro)\b/) ??
    textLower.match(/(?:eur|euro)\s*(\d+(?:[.,]\d+)?)\b/) ??
    textLower.match(/(?:=|auf|to|at)\s*(\d+(?:[.,]\d+)?)\b/);

  if (eurMatch && target && containsPriceWord) {
    const price = Math.max(0, parseFloat(eurMatch[1].replace(",", ".")));
    const mode: "total_price_eur" | "unit_price_eur" = containsTotalWord
      ? "total_price_eur"
      : "unit_price_eur";

    if (target.kind === "pos") {
      const override: ManualOverride =
        mode === "total_price_eur"
          ? {
              target: "pos",
              pos_nr: target.pos_nr,
              mode: "total_price_eur",
              total_price_eur: price,
            }
          : {
              target: "pos",
              pos_nr: target.pos_nr,
              mode: "unit_price_eur",
              unit_price_eur: price,
            };
      const key = mode === "total_price_eur" ? "accepted_pos_total" : "accepted_pos_price";
      return {
        override,
        feedback: t(lang, key, { price: price.toFixed(2), target: target.display }),
      };
    }

    const override: ManualOverride =
      mode === "total_price_eur"
        ? {
            target: "artikel",
            artikel_nr: target.artikel_nr,
            mode: "total_price_eur",
            total_price_eur: price,
          }
        : {
            target: "artikel",
            artikel_nr: target.artikel_nr,
            mode: "unit_price_eur",
            unit_price_eur: price,
          };
    const key = mode === "total_price_eur" ? "accepted_art_total" : "accepted_art_price";
    return {
      override,
      feedback: t(lang, key, { price: price.toFixed(2), target: target.display }),
    };
  }

  if (target && containsPriceWord) {
    return { override: null, feedback: t(lang, "price_missing_value") };
  }
  if (eurMatch && !target) {
    return { override: null, feedback: t(lang, "price_target_missing") };
  }

  return { override: null, feedback: "" };
}

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.max(min, Math.min(max, value));
}
