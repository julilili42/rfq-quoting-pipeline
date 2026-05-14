import type { Anfrage, Position } from "@/shared/schemas/anfrage";
import type { ManualOverride } from "@/shared/schemas/quotation";

const HEADER_FIELDS = [
  "kunde_firma",
  "kunde_ansprechpartner",
  "kunde_email",
  "kundennummer",
  "belegnummer",
  "datum",
  "incoterms",
  "zahlungsbedingungen",
] as const;

const POSITION_FIELDS = [
  "artikelnummer",
  "bezeichnung",
  "menge",
  "einheit",
  "lieferzeit",
  "lieferwerk",
  "werkstoff",
  "werkstoff_alternativen",
  "zeichnungsnummer",
  "abmessungen",
  "gewicht_stueck_kg",
  "ist_zertifikat",
] as const satisfies readonly (keyof Position)[];

export function calculateChangedFields(
  original: Anfrage | null | undefined,
  current: Anfrage,
  overrides: ManualOverride[] = [],
): Set<string> {
  if (!original) return new Set();

  const changed = new Set<string>();

  for (const field of HEADER_FIELDS) {
    if (!sameValue(original[field], current[field])) {
      changed.add(field);
    }
  }

  const originalByPos = new Map(original.positionen.map((pos) => [pos.pos_nr, pos]));
  const currentByPos = new Map(current.positionen.map((pos) => [pos.pos_nr, pos]));
  const currentIndexByPos = new Map(
    current.positionen.map((pos, index) => [pos.pos_nr, index]),
  );

  for (const originalPos of original.positionen) {
    const currentPos = currentByPos.get(originalPos.pos_nr);
    if (!currentPos) {
      changed.add(`positionen[delete:${originalPos.pos_nr}]`);
      continue;
    }

    const index = currentIndexByPos.get(originalPos.pos_nr) ?? 0;
    for (const field of POSITION_FIELDS) {
      if (!sameValue(originalPos[field], currentPos[field])) {
        changed.add(`positionen[${index}].${field}`);
      }
    }
  }

  for (const currentPos of current.positionen) {
    if (!originalByPos.has(currentPos.pos_nr)) {
      changed.add(`positionen[add:${currentPos.pos_nr}]`);
    }
  }

  addOverrideChanges(changed, current, overrides);

  return changed;
}

function addOverrideChanges(
  changed: Set<string>,
  current: Anfrage,
  overrides: ManualOverride[],
) {
  const currentIndexByPos = new Map(
    current.positionen.map((pos, index) => [pos.pos_nr, index]),
  );

  for (const override of overrides) {
    const field = fieldForOverrideMode(override.mode);
    if (override.target === "pos") {
      const index = currentIndexByPos.get(override.pos_nr);
      if (index == null) continue;
      changed.add(`positionen[${index}].${field}`);
      continue;
    }
    changed.add(`artikel[${override.artikel_nr}].${field}`);
  }
}

function fieldForOverrideMode(mode: ManualOverride["mode"]): string {
  switch (mode) {
    case "unit_price_eur":
      return "einzelpreis";
    case "total_price_eur":
      return "gesamtpreis";
    case "discount_pct":
      return "rabatt";
    case "disable_volume_discount":
      return "mengenrabatt";
  }
}

function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) return false;
    if (a.length !== b.length) return false;
    return a.every((value, index) => sameValue(value, b[index]));
  }

  if (typeof a === "number" || typeof b === "number") {
    const left = toNumberOrNull(a);
    const right = toNumberOrNull(b);
    if (left == null || right == null) return left === right;
    return Math.abs(left - right) < 0.000001;
  }

  return normalizeScalar(a) === normalizeScalar(b);
}

function normalizeScalar(value: unknown): unknown {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  return value;
}

function toNumberOrNull(value: unknown): number | null {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
