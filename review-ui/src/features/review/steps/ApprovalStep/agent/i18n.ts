/**
 * Agent chat translations.
 *
 * Mirrors the strings in `quoting/ui/review_agent.py::_t`. We keep the
 * exact same keys so behaviour stays identical and tests on the Python
 * side remain a useful spec for the React side.
 */

export type AgentLang = "de" | "en";

const TABLE: Record<AgentLang, Record<string, string>> = {
  de: {
    discount_missing_pct:
      "Bitte gib den Rabatt in Prozent an, z. B. 7%.",
    accepted_pos:
      "Verstanden: Rabatt {pct}% für Position {target}.",
    accepted_art:
      "Verstanden: Rabatt {pct}% für Artikel {target}.",
    accepted_pos_price:
      "Verstanden: Position {target} auf {price} EUR gesetzt.",
    accepted_art_price:
      "Verstanden: Artikel {target} auf {price} EUR gesetzt.",
    accepted_pos_total:
      "Verstanden: Gesamtpreis für Position {target} auf {price} EUR gesetzt.",
    accepted_art_total:
      "Verstanden: Gesamtpreis für Artikel {target} auf {price} EUR gesetzt.",
    discount_target_missing:
      "Kein Rabattziel erkannt. Bitte Artikel oder Position angeben (z. B. pos 2).",
    price_target_missing:
      "Kein Preisziel erkannt. Bitte Artikel oder Position angeben (z. B. pos 3 = 10 EUR).",
    price_missing_value:
      "Bitte gib einen Betrag in EUR an, z. B. 10 EUR.",
    reply_total:
      "Aktuelle Gesamtsumme: {total}.",
    reply_no_warnings: "Keine kritischen Warnungen vorhanden.",
    reply_warnings_header: "Warnungen:",
    reply_help:
      "Ich kann kaufmännische Anpassungen anwenden und das PDF direkt neu berechnen. Beispiele: 'Gib 5% Rabatt auf Artikel ABC' oder 'Setze pos 3 auf 10 EUR'.",
    intro:
      "Beispiele: *5% Rabatt auf Artikel ABC*, *Setze pos 3 auf 12 EUR*, *Wie hoch ist die Summe?*",
    chat_placeholder:
      "Schreibe eine Anpassung: Rabatt je Position/Artikel oder Summenfrage",
    rebuilding: "Anpassung wird angewendet und PDF neu berechnet…",
    rebuild_failed: "Anpassung konnte nicht angewendet werden: {error}",
  },
  en: {
    discount_missing_pct: "Please provide a discount percentage, e.g. 7%.",
    accepted_pos: "Applied: {pct}% discount for position {target}.",
    accepted_art: "Applied: {pct}% discount for article {target}.",
    accepted_pos_price: "Applied: position {target} unit price set to {price} EUR.",
    accepted_art_price: "Applied: article {target} unit price set to {price} EUR.",
    accepted_pos_total: "Applied: total price for position {target} set to {price} EUR.",
    accepted_art_total: "Applied: total price for article {target} set to {price} EUR.",
    discount_target_missing:
      "I couldn't identify the discount target. Please specify article or position (e.g. pos 2).",
    price_target_missing:
      "I couldn't identify the price target. Please specify article or position (e.g. pos 3 = 10 EUR).",
    price_missing_value: "Please provide an amount in EUR, e.g. 10 EUR.",
    reply_total: "Current total amount: {total}.",
    reply_no_warnings: "No critical warnings.",
    reply_warnings_header: "Warnings:",
    reply_help:
      "I can apply commercial edits and immediately regenerate the PDF. Examples: 'Apply 5% discount on article ABC' or 'Set pos 3 to 10 EUR'.",
    intro:
      "Try: *Discount 5% on article ABC*, *Set pos 3 to 12 EUR*, *What is the total?*",
    chat_placeholder:
      "Write an edit: discount by position/article, or total question",
    rebuilding: "Applying edit and recalculating PDF…",
    rebuild_failed: "Could not apply edit: {error}",
  },
};

export function t(
  lang: AgentLang,
  key: string,
  vars: Record<string, string | number> = {},
): string {
  const template = TABLE[lang][key] ?? TABLE.de[key] ?? key;
  return Object.entries(vars).reduce(
    (acc, [k, v]) => acc.replaceAll(`{${k}}`, String(v)),
    template,
  );
}
