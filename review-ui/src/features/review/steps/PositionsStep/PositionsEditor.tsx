import * as Accordion from "@radix-ui/react-accordion";
import { Plus } from "lucide-react";
import { useCallback, useMemo, useRef } from "react";

import { Button } from "@/shared/components/ui/button";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import type { Anfrage, Position } from "@/shared/schemas/anfrage";
import type { MatchResult } from "@/shared/schemas/matchResult";
import type {
  ManualOverride,
  Quotation,
  QuotationItem,
} from "@/shared/schemas/quotation";

import { useSaveAndRegenerate } from "../../hooks/useReviewMutations";
import { ChangedFieldsIndicator } from "../../components/ChangedFieldsIndicator";
import { MatchSummary } from "./MatchSummary";
import { PositionCard } from "./PositionCard";
import { upsertOverride } from "./upsertOverride";

interface PositionsEditorProps {
  reviewId: string;
  anfrage: Anfrage;
  matches: MatchResult[];
  quotation: Quotation | null;
  overrides: ManualOverride[];
}

/**
 * Step-1 editor.
 *
 * CRUD operations are intentionally narrow:
 *
 * - **Edit**: per-field commits via `useSaveAndRegenerate`. The draft
 *   PDF rebuilds in the same round-trip, so what the user types is
 *   what they see in the iframe (eventually — there's a brief network
 *   round-trip).
 * - **Manual re-match**: handled inside `StammdatenSearchDialog`,
 *   which lives on the `PositionCard`. Editor doesn't need to wire
 *   anything up.
 * - **Add position**: appends a new `Position` with the next free
 *   `pos_nr`. The new card is auto-opened so the user can fill it in
 *   immediately.
 * - **Delete position**: filters the position out and pushes the new
 *   Anfrage to the backend, which re-runs pricing. Manual overrides
 *   targeting the deleted `pos_nr` are dropped at the same time so
 *   they don't linger as orphans.
 *
 * Pos numbers are **never renumbered** on delete. The backend's
 * matches and overrides are keyed on `pos_nr`; renumbering would mean
 * silently rewiring relationships that the user expects to stay
 * stable. If a user deletes pos 3 of 5, the remaining positions stay
 * 1, 2, 4, 5.
 */
export function PositionsEditor({
  reviewId,
  anfrage,
  matches,
  quotation,
  overrides,
}: PositionsEditorProps) {
  const trackChange = useReviewUiStore((s) => s.trackChange);
  const saveAndRegenerate = useSaveAndRegenerate(reviewId);

  // Track which pos_nrs were just added in this session, so we can
  // auto-expand them and visually distinguish them.
  const newlyAddedRef = useRef<Set<number>>(new Set());

  const matchesByPos = useMemo(() => {
    const map = new Map<number, MatchResult>();
    for (const m of matches) map.set(m.pos_nr, m);
    return map;
  }, [matches]);

  const quotationByPos = useMemo(() => {
    const map = new Map<number, QuotationItem>();
    for (const it of quotation?.items ?? []) map.set(it.pos_nr, it);
    return map;
  }, [quotation]);

  const unitPriceOverrideByPos = useMemo(() => {
    const map = new Map<number, number>();
    for (const o of overrides) {
      if (o.target === "pos" && o.mode === "unit_price_eur") {
        map.set(o.pos_nr, o.unit_price_eur);
      }
    }
    return map;
  }, [overrides]);

  const handlePositionChange = useCallback(
    (next: Position, original: Position) => {
      if (JSON.stringify(next) === JSON.stringify(original)) return;
      const updated: Anfrage = {
        ...anfrage,
        positionen: anfrage.positionen.map((p) =>
          p.pos_nr === next.pos_nr ? next : p,
        ),
      };
      saveAndRegenerate.mutate({ anfrage: updated });
    },
    [anfrage, saveAndRegenerate],
  );

  const handleUnitPriceChange = useCallback(
    (override: ManualOverride | null) => {
      if (!override) return;
      const updated = upsertOverride(overrides, override);
      saveAndRegenerate.mutate({ overrides: updated });
    },
    [overrides, saveAndRegenerate],
  );

  const handleDeletePosition = useCallback(
    (posNr: number) => {
      const updatedAnfrage: Anfrage = {
        ...anfrage,
        positionen: anfrage.positionen.filter((p) => p.pos_nr !== posNr),
      };

      // Drop any overrides that targeted this position — they would
      // otherwise resurface if the user accidentally re-adds the same
      // pos_nr later, which is confusing.
      const updatedOverrides = overrides.filter(
        (o) => !(o.target === "pos" && o.pos_nr === posNr),
      );

      trackChange(`positionen[delete:${posNr}]`);
      saveAndRegenerate.mutate({
        anfrage: updatedAnfrage,
        overrides:
          updatedOverrides.length !== overrides.length ? updatedOverrides : undefined,
      });
    },
    [anfrage, overrides, saveAndRegenerate, trackChange],
  );

  const handleAddPosition = useCallback(() => {
    // Pick the next free pos_nr — max + 1, ensuring uniqueness even
    // after deletes (so we never accidentally collide with the pos_nr
    // of a row the user deleted earlier).
    const used = new Set(anfrage.positionen.map((p) => p.pos_nr));
    let nextPosNr = anfrage.positionen.length + 1;
    while (used.has(nextPosNr)) nextPosNr += 1;

    const blank: Position = {
      pos_nr: nextPosNr,
      artikelnummer: "",
      bezeichnung: "",
      menge: 1,
      einheit: "Stk",
      liefertermin: null,
      lieferzeit: null,
      lieferwerk: null,
      werkstoff: null,
      werkstoff_alternativen: [],
      zeichnungsnummer: null,
      abmessungen: null,
      gewicht_stueck_kg: null,
      ist_zertifikat: false,
      confidence: "low",
      source_quote: "",
    };

    newlyAddedRef.current.add(nextPosNr);
    trackChange(`positionen[add:${nextPosNr}]`);

    saveAndRegenerate.mutate({
      anfrage: { ...anfrage, positionen: [...anfrage.positionen, blank] },
    });
  }, [anfrage, saveAndRegenerate, trackChange]);

  // Open all newly-added positions by default. Existing positions stay
  // collapsed (matching the historical Streamlit behaviour).
  const defaultOpenValues = useMemo(
    () =>
      anfrage.positionen
        .filter((p) => newlyAddedRef.current.has(p.pos_nr))
        .map((p) => `pos-${p.pos_nr}`),
    [anfrage.positionen],
  );

  return (
    <section aria-labelledby="positions-heading" className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="positions-heading" className="section-label mb-2">
            Positionen prüfen
          </h2>
          <ChangedFieldsIndicator />
          <MatchSummary matches={matches} />
        </div>

        {saveAndRegenerate.isPending && (
          <span className="text-xs font-semibold text-info">
            PDF wird neu berechnet…
          </span>
        )}
        {saveAndRegenerate.isError && (
          <span className="text-xs font-semibold text-danger">
            Speichern fehlgeschlagen — bitte erneut versuchen.
          </span>
        )}
      </header>

      <Accordion.Root
        type="multiple"
        defaultValue={defaultOpenValues}
        className="space-y-2"
      >
        {anfrage.positionen.map((position, index) => (
          <PositionCard
            key={position.pos_nr}
            reviewId={reviewId}
            index={index}
            position={position}
            match={matchesByPos.get(position.pos_nr)}
            quotationItem={quotationByPos.get(position.pos_nr)}
            unitPriceOverride={unitPriceOverrideByPos.get(position.pos_nr)}
            defaultOpen={newlyAddedRef.current.has(position.pos_nr)}
            onPositionChange={(next) => handlePositionChange(next, position)}
            onUnitPriceChange={handleUnitPriceChange}
            onFieldEdit={trackChange}
            onDelete={() => handleDeletePosition(position.pos_nr)}
          />
        ))}
      </Accordion.Root>

      <div className="flex justify-center pt-2">
        <Button
          type="button"
          variant="secondary"
          onClick={handleAddPosition}
          disabled={saveAndRegenerate.isPending}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Neue Position hinzufügen
        </Button>
      </div>
    </section>
  );
}
