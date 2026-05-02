import type { AgentLang } from "./i18n";

const CYRILLIC_RE = /[А-Яа-яЁё]/;

const DE_HINTS = [
  " und ", " der ", " die ", " das ", " mit ", " für ",
  "anfrage", "angebot", "liefertermin", "menge", "artikel",
];
const EN_HINTS = [
  " and ", " the ", " with ", "request", "quotation",
  "delivery", "quantity", "discount", "product",
];

/**
 * Detect preferred chat language from any free-text sample.
 *
 * Mirrors `quoting/ui/review_agent.detect_agent_language`. We default
 * to German because that's what the data is overwhelmingly in.
 * Cyrillic content gets bumped to English (the fallback), since we
 * don't ship a Russian translation table.
 */
export function detectAgentLanguage(text: string, fallback = ""): AgentLang {
  const sample = `${text ?? ""} ${fallback}`.trim();
  if (!sample) return "de";
  if (CYRILLIC_RE.test(sample)) return "en";

  const lower = sample.toLowerCase();
  const de = DE_HINTS.reduce((n, h) => n + (lower.split(h).length - 1), 0);
  const en = EN_HINTS.reduce((n, h) => n + (lower.split(h).length - 1), 0);
  return de >= en ? "de" : "en";
}
