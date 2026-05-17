import * as Accordion from "@radix-ui/react-accordion";
import { Plus } from "lucide-react";
import { useCallback, useMemo, useRef } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { Button } from "@/shared/components/ui/button";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import { useDelayedVisible } from "@/shared/hooks/useDelayedVisible";
import type { Anfrage, Position } from "@/shared/schemas/anfrage";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";
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
  onEvidenceSelect?: (target: SourceNavigationTarget) => void;
  showChangeIndicator?: boolean;
}

/**
 * Position editor inside the combined request-data step.
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
  onEvidenceSelect,
  showChangeIndicator = true,
}: PositionsEditorProps) {
  const trackChange = useReviewUiStore((s) => s.trackChange);
  const refreshChangedFields = useReviewUiStore((s) => s.refreshChangedFields);
  const recordUndoSnapshot = useReviewUiStore((s) => s.recordUndoSnapshot);
  const saveAndRegenerate = useSaveAndRegenerate(reviewId);
  const showSaveStatus = useDelayedVisible(saveAndRegenerate.isPending);

  // Track which pos_nrs were just added in this session, so we can
  // auto-expand them and visually distinguish them.
  const newlyAddedRef = useRef<Set<number>>(new Set());

  const activePosNrs = useMemo(
    () => new Set(anfrage.positionen.map((p) => p.pos_nr)),
    [anfrage.positionen],
  );

  const activeMatches = useMemo(
    () => matches.filter((m) => activePosNrs.has(m.pos_nr)),
    [matches, activePosNrs],
  );

  const matchesByPos = useMemo(() => {
    const map = new Map<number, MatchResult>();
    for (const m of activeMatches) map.set(m.pos_nr, m);
    return map;
  }, [activeMatches]);

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

  const discountDisabledByPos = useMemo(() => {
    const set = new Set<number>();
    for (const o of overrides) {
      if (o.target === "pos" && o.mode === "disable_volume_discount") {
        set.add(o.pos_nr);
      }
    }
    return set;
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
      recordUndoSnapshot();
      refreshChangedFields(updated);
      saveAndRegenerate.mutate({ anfrage: updated });
    },
    [anfrage, recordUndoSnapshot, refreshChangedFields, saveAndRegenerate],
  );

  const handleUnitPriceChange = useCallback(
    (override: ManualOverride | null) => {
      if (!override) return;
      const updated = upsertOverride(overrides, override);
      recordUndoSnapshot();
      refreshChangedFields(anfrage, updated);
      saveAndRegenerate.mutate({ overrides: updated });
    },
    [anfrage, overrides, recordUndoSnapshot, refreshChangedFields, saveAndRegenerate],
  );

  const handleDisableDiscountChange = useCallback(
    (posNr: number, disabled: boolean) => {
      const updated = disabled
        ? upsertOverride(overrides, { target: "pos", pos_nr: posNr, mode: "disable_volume_discount" })
        : overrides.filter(
            (o) => !(o.target === "pos" && o.mode === "disable_volume_discount" && o.pos_nr === posNr),
          );
      recordUndoSnapshot();
      refreshChangedFields(anfrage, updated);
      saveAndRegenerate.mutate({ overrides: updated });
    },
    [anfrage, overrides, recordUndoSnapshot, refreshChangedFields, saveAndRegenerate],
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

      recordUndoSnapshot();
      trackChange(`positionen[delete:${posNr}]`);
      refreshChangedFields(updatedAnfrage, updatedOverrides);
      saveAndRegenerate.mutate({
        anfrage: updatedAnfrage,
        overrides:
          updatedOverrides.length !== overrides.length ? updatedOverrides : undefined,
      });
    },
    [anfrage, overrides, recordUndoSnapshot, refreshChangedFields, saveAndRegenerate, trackChange],
  );

  const handleAddPosition = useCallback(() => {
    // Pick the next free pos_nr — max + 1, ensuring uniqueness even
    // after deletes (so we never accidentally collide with the pos_nr
    // of a row the user deleted earlier).
    const maxPosNr = anfrage.positionen.reduce(
      (max, position) => Math.max(max, position.pos_nr),
      0,
    );
    const nextPosNr = maxPosNr + 1;

    const blank: Position = {
      pos_nr: nextPosNr,
      artikelnummer: "",
      bezeichnung: "",
      menge: 1,
      einheit: "Stk",
      lieferzeit: null,
      lieferwerk: null,
      werkstoff: null,
      werkstoff_alternativen: [],
      abmessungen: null,
      gewicht_stueck_kg: null,
      ist_zertifikat: false,
      confidence: "low",
      source_quote: "",
    };

    newlyAddedRef.current.add(nextPosNr);
    recordUndoSnapshot();
    trackChange(`positionen[add:${nextPosNr}]`);
    refreshChangedFields({
      ...anfrage,
      positionen: [...anfrage.positionen, blank],
    });

    saveAndRegenerate.mutate({
      anfrage: { ...anfrage, positionen: [...anfrage.positionen, blank] },
    });
  }, [anfrage, recordUndoSnapshot, refreshChangedFields, saveAndRegenerate, trackChange]);

  useHotkeys("alt+n", handleAddPosition, {
    enabled: !saveAndRegenerate.isPending,
    preventDefault: true,
  });

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
    <section
      id="positions-data"
      aria-labelledby="positions-heading"
      className="scroll-mt-6 space-y-4"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="positions-heading" className="section-label mb-2">
            Positionen
          </h2>
          <MatchSummary matches={activeMatches} />
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          {showChangeIndicator && <ChangedFieldsIndicator />}
          {showSaveStatus && (
            <span className="text-xs font-medium text-muted-foreground" role="status">
              Änderungen werden gespeichert…
            </span>
          )}
          {saveAndRegenerate.isError && (
            <span className="text-xs font-semibold text-danger">
              PDF-Neuberechnung fehlgeschlagen — Daten wurden gespeichert. Bitte erneut versuchen.
            </span>
          )}
        </div>
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
            discountDisabled={discountDisabledByPos.has(position.pos_nr)}
            defaultOpen={newlyAddedRef.current.has(position.pos_nr)}
            onPositionChange={(next) => handlePositionChange(next, position)}
            onUnitPriceChange={handleUnitPriceChange}
            onDiscountDisabledChange={(disabled) => handleDisableDiscountChange(position.pos_nr, disabled)}
            onFieldEdit={trackChange}
            onDelete={() => handleDeletePosition(position.pos_nr)}
            onEvidenceSelect={onEvidenceSelect}
          />
        ))}
      </Accordion.Root>

      <div className="flex justify-center pt-2">
        <div className="group relative">
          <Button
            type="button"
            variant="secondary"
            onClick={handleAddPosition}
            disabled={saveAndRegenerate.isPending}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Neue Position hinzufügen
          </Button>
          <ShortcutHint keys={["Alt", "N"]} />
        </div>
      </div>
    </section>
  );
}
