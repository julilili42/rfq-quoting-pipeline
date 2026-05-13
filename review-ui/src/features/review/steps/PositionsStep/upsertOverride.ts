import type { ManualOverride } from "@/shared/schemas/quotation";

/**
 * Replace an override targeting the same pos/article, or append a new one.
 * Mirrors `quoting/ui/review_agent.upsert_override`.
 */
export function upsertOverride(
  list: ManualOverride[],
  next: ManualOverride,
): ManualOverride[] {
  const matches = (a: ManualOverride, b: ManualOverride) => {
    if (a.target !== b.target || a.mode !== b.mode) return false;
    if (a.target === "pos" && b.target === "pos") return a.pos_nr === b.pos_nr;
    if (a.target === "artikel" && b.target === "artikel")
      return a.artikel_nr === b.artikel_nr;
    return false;
  };

  let replaced = false;
  const merged = list.map((item) => {
    if (matches(item, next)) {
      replaced = true;
      return next;
    }
    return item;
  });
  if (!replaced) merged.push(next);
  return merged;
}
