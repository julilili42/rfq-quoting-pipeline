import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown, Replace, Trash2 } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { FormField } from "@/shared/components/ui/FormField";
import { Input } from "@/shared/components/ui/input";
import { SourceBadge } from "@/shared/components/ui/SourceBadge";
import { cn } from "@/shared/lib/cn";
import { formatEur } from "@/shared/lib/format";
import type { Evidence, Position } from "@/shared/schemas/anfrage";
import type { MatchResult } from "@/shared/schemas/matchResult";
import type { ManualOverride, QuotationItem } from "@/shared/schemas/quotation";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

import { MatchChip } from "./MatchChip";
import { StammdatenSearchDialog } from "./StammdatenSearchDialog";

interface PositionCardProps {
  reviewId: string;
  position: Position;
  match?: MatchResult;
  quotationItem?: QuotationItem;
  unitPriceOverride?: number;
  /** Auto-open the accordion on mount — used right after "add position". */
  defaultOpen?: boolean;
  onPositionChange: (next: Position) => void;
  onUnitPriceChange: (override: ManualOverride | null) => void;
  onFieldEdit: (fieldPath: string) => void;
  onDelete: () => void;
  onEvidenceSelect?: (ev: Evidence) => void;
  index: number;
}

const VOLUME_TIERS = [
  { label: "< 100 Stk.", minQty: 0,    rabatt: 0  },
  { label: "100–499",    minQty: 100,  rabatt: 5  },
  { label: "500–999",    minQty: 500,  rabatt: 10 },
  { label: "≥ 1.000",   minQty: 1000, rabatt: 15 },
] as const;

function activeTierIndex(qty: number): number {
  for (let i = VOLUME_TIERS.length - 1; i >= 0; i--) {
    if (qty >= VOLUME_TIERS[i].minQty) return i;
  }
  return 0;
}

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "hoch",
  medium: "mittel",
  low: "gering",
};

/**
 * Editable position panel.
 *
 * The card keeps its own draft state for every text field so React's
 * controlled-input model doesn't fight the user's typing. We commit on
 * `onBlur` to keep PDF rebuilds from firing per keystroke.
 *
 * Two destructive actions live on this card:
 *
 * - **Anderen Artikel zuordnen** opens the Stammdaten search dialog,
 *   which writes a manual match server-side. The card itself doesn't
 *   know about the mutation — the dialog handles it.
 * - **Position löschen** uses inline two-step confirmation. We never
 *   delete on a single click, but we also don't pop a modal — the
 *   confirmation lives in the same row, identical pattern to the
 *   "Pipeline reset" sidebar action.
 */
export function PositionCard({
  reviewId,
  position,
  match,
  quotationItem,
  unitPriceOverride,
  defaultOpen = false,
  onPositionChange,
  onUnitPriceChange,
  onFieldEdit,
  onDelete,
  onEvidenceSelect,
  index,
}: PositionCardProps) {
  const [draft, setDraft] = useState<Position>(position);
  useEffect(() => setDraft(position), [position]);

  const updateField = <K extends keyof Position>(key: K, value: Position[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const commit = (fieldPath: string) => {
    if (JSON.stringify(draft) !== JSON.stringify(position)) {
      onFieldEdit(fieldPath);
      onPositionChange(draft);
    }
  };

  const handleAssign = (row: StammdatenRow) => {
    const updated: Position = {
      ...draft,
      artikelnummer: row.artikel_nr,
      bezeichnung: row.bezeichnung || draft.bezeichnung,
      werkstoff: row.werkstoff ?? draft.werkstoff,
      abmessungen: row.abmessungen ?? draft.abmessungen,
      einheit: row.einheit || draft.einheit,
    };
    setDraft(updated);
    onPositionChange(updated);
    onFieldEdit(`positionen[${index}].artikelnummer`);
  };

  const initialUnitPrice =
    unitPriceOverride ?? quotationItem?.einzelpreis ?? 0;
  const [unitPriceDraft, setUnitPriceDraft] = useState<number>(initialUnitPrice);
  useEffect(() => setUnitPriceDraft(initialUnitPrice), [initialUnitPrice]);

  const commitUnitPrice = () => {
    if (Math.abs(unitPriceDraft - initialUnitPrice) < 0.005) return;
    onUnitPriceChange({
      target: "pos",
      pos_nr: position.pos_nr,
      mode: "unit_price_eur",
      unit_price_eur: Math.max(0, Number(unitPriceDraft.toFixed(2))),
    });
    onFieldEdit(`positionen[${index}].einzelpreis`);
  };

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const label = `Pos ${position.pos_nr} · ${
    position.artikelnummer || "Unbekannt"
  } · ${Math.round(position.menge)} ${position.einheit}`;

  return (
    <Accordion.Item
      value={`pos-${position.pos_nr}`}
      className={cn(
        "rounded-lg border bg-surface shadow-card transition-colors",
        confirmingDelete ? "border-danger/40" : "border-border hover:border-foreground/20",
      )}
    >
      <Accordion.Header className="flex items-stretch">
        <Accordion.Trigger
          className={cn(
            "group flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left text-sm font-semibold",
            "data-[state=open]:border-b data-[state=open]:border-border",
          )}
        >
          <span className="truncate">{label}</span>
          <ChevronDown
            className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
            aria-hidden="true"
          />
        </Accordion.Trigger>

        {/* Delete — always visible, separate click target */}
        {confirmingDelete ? (
          <div className="flex items-center gap-1.5 border-b border-danger/30 border-l border-l-danger/20 bg-danger-soft px-3">
            <span className="text-[11px] font-semibold text-danger whitespace-nowrap">Löschen?</span>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setConfirmingDelete(false); onDelete(); }}
              className="rounded px-1.5 py-0.5 text-[11px] font-bold text-danger bg-danger/10 hover:bg-danger/20"
            >
              Ja
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setConfirmingDelete(false); }}
              className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              Nein
            </button>
          </div>
        ) : (
          <button
            type="button"
            aria-label={`Position ${position.pos_nr} löschen`}
            onClick={(e) => { e.stopPropagation(); setConfirmingDelete(true); }}
            className="flex items-center border-l border-border px-3 text-muted-foreground/40 transition-colors hover:bg-danger-soft hover:text-danger data-[state=open]:border-b data-[state=open]:border-border"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </Accordion.Header>

      <Accordion.Content
        className="px-4 pb-4 pt-3 data-[state=closed]:hidden"
        forceMount={defaultOpen ? true : undefined}
      >
        {/* Match row + KI badge */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {match ? <MatchChip match={match} /> : <span />}
          <span className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold",
            position.confidence === "high"
              ? "bg-success/10 text-success"
              : position.confidence === "medium"
                ? "bg-warning/10 text-warning"
                : "bg-danger/10 text-danger",
          )}>
            KI {CONFIDENCE_LABEL[position.confidence] ?? position.confidence}
          </span>
          <div className="ml-auto">
            <StammdatenSearchDialog
              reviewId={reviewId}
              posNr={position.pos_nr}
              initialQuery={position.artikelnummer || position.bezeichnung}
              onAssign={handleAssign}
            >
              <Button type="button" size="sm" variant="ghost" className="border border-border">
                <Replace className="h-3.5 w-3.5" aria-hidden="true" />
                Anderen Artikel zuordnen
              </Button>
            </StammdatenSearchDialog>
          </div>
        </div>

        {/* PRIMARY DATA BLOCK */}
        {(() => {
          const qty = draft.menge;
          const activeIdx = activeTierIndex(qty);
          const tier = VOLUME_TIERS[activeIdx];
          const basis = quotationItem?.basispreis_eur ?? 0;
          const hasOverride = unitPriceOverride != null;
          const discountedPrice = basis > 0 && tier.rabatt > 0 ? basis * (1 - tier.rabatt / 100) : basis;
          const ersparnis = basis > 0 && tier.rabatt > 0 ? basis * (tier.rabatt / 100) : 0;
          const showStaffel = !!quotationItem && !draft.ist_zertifikat;

          return (
            <div className="overflow-hidden rounded-xl border border-border">
              {/* Metric row */}
              <div className="grid grid-cols-3 divide-x divide-border">
                <div className="flex flex-col gap-1.5 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Menge</p>
                  <div className="flex items-baseline gap-2">
                    <Input
                      type="number"
                      step="any"
                      value={draft.menge}
                      onChange={(e) => updateField("menge", Number(e.target.value))}
                      onBlur={() => commit(`positionen[${index}].menge`)}
                      className="h-auto min-w-0 flex-1 border-0 bg-transparent p-0 text-xl font-bold shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    />
                    <Input
                      value={draft.einheit}
                      onChange={(e) => updateField("einheit", e.target.value)}
                      onBlur={() => commit(`positionen[${index}].einheit`)}
                      className="h-auto w-14 shrink-0 border-0 bg-transparent p-0 text-sm font-semibold text-muted-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-1 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Lieferung</p>
                  <Input
                    value={draft.lieferzeit ?? ""}
                    onChange={(e) => updateField("lieferzeit", e.target.value)}
                    onBlur={() => commit(`positionen[${index}].lieferzeit`)}
                    className="h-auto border-0 bg-transparent p-0 text-xl font-bold shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    placeholder="z. B. 6 Wo."
                  />
                  <Input
                    value={draft.lieferwerk ?? ""}
                    onChange={(e) => updateField("lieferwerk", e.target.value)}
                    onBlur={() => commit(`positionen[${index}].lieferwerk`)}
                    className="h-auto border-0 bg-transparent p-0 text-xs font-medium text-muted-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    placeholder="Werk"
                  />
                </div>

                <div className="flex flex-col gap-1.5 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Stückpreis EUR
                    {hasOverride && (
                      <span className="ml-1.5 text-warning">Override</span>
                    )}
                  </p>
                  <Input
                    type="number"
                    step="0.01"
                    value={unitPriceDraft}
                    onChange={(e) => setUnitPriceDraft(Number(e.target.value))}
                    onBlur={commitUnitPrice}
                    className="h-auto border-0 bg-transparent p-0 text-xl font-bold shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    placeholder="—"
                  />
                </div>
              </div>

              {/* Mengenstaffel — innerhalb des Blocks */}
              {showStaffel && (
                <div className="border-t border-border bg-muted/30 px-4 py-2.5">
                  <div className="flex items-center">
                    {VOLUME_TIERS.map((t, i) => (
                      <Fragment key={t.label}>
                        <span className={cn(
                          "whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                          i === activeIdx ? "bg-brand text-white"
                            : i < activeIdx ? "text-muted-foreground/40"
                            : "text-muted-foreground",
                        )}>
                          {t.label}{t.rabatt > 0 && ` –${t.rabatt}%`}
                        </span>
                        {i < VOLUME_TIERS.length - 1 && (
                          <div className={cn("h-px min-w-[12px] flex-1", i < activeIdx ? "bg-muted-foreground/20" : "bg-border")} />
                        )}
                      </Fragment>
                    ))}
                  </div>
                  {basis > 0 && !hasOverride && tier.rabatt > 0 && (
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      <span className="tabular-nums">{formatEur(basis)}</span>
                      <span className="mx-1.5 text-foreground/30">→</span>
                      <span className="font-medium text-brand">–{tier.rabatt}% Mengenrabatt</span>
                      <span className="mx-1.5 text-foreground/30">→</span>
                      <span className="font-semibold text-foreground tabular-nums">{formatEur(discountedPrice)}/Stk.</span>
                      <span className="ml-3 font-medium text-brand tabular-nums">–{formatEur(ersparnis)}/Stk.</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* BEZEICHNUNG */}
        <div className="mt-4">
          <FormField label="Bezeichnung">
            <textarea
              className="flex min-h-[104px] w-full rounded-md border border-input bg-surface px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={draft.bezeichnung}
              onChange={(e) => updateField("bezeichnung", e.target.value)}
              onBlur={() => commit(`positionen[${index}].bezeichnung`)}
            />
          </FormField>
        </div>

        {/* WEITERE DETAILS — divider-style toggle */}
        <button
          type="button"
          onClick={() => setDetailsOpen((o) => !o)}
          className="mt-5 flex w-full items-center gap-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <div className="h-px flex-1 bg-border" />
          <span className="flex shrink-0 items-center gap-1 font-medium">
            <ChevronDown
              className={cn("h-3 w-3 transition-transform duration-200", detailsOpen && "rotate-180")}
              aria-hidden="true"
            />
            Weitere Details
          </span>
          <div className="h-px flex-1 bg-border" />
        </button>

        {detailsOpen && (
          <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
            <FormField label="Artikelnummer">
              <Input
                value={draft.artikelnummer}
                onChange={(e) => updateField("artikelnummer", e.target.value)}
                onBlur={() => commit(`positionen[${index}].artikelnummer`)}
              />
            </FormField>

            <FormField label="Werkstoff">
              <Input
                value={draft.werkstoff ?? ""}
                onChange={(e) => updateField("werkstoff", e.target.value)}
                onBlur={() => commit(`positionen[${index}].werkstoff`)}
              />
            </FormField>

            <FormField label="Zeichnungs-Nr.">
              <Input
                value={draft.zeichnungsnummer ?? ""}
                onChange={(e) => updateField("zeichnungsnummer", e.target.value)}
                onBlur={() => commit(`positionen[${index}].zeichnungsnummer`)}
              />
            </FormField>

            <FormField label="Abmessungen">
              <Input
                value={draft.abmessungen ?? ""}
                onChange={(e) => updateField("abmessungen", e.target.value)}
                onBlur={() => commit(`positionen[${index}].abmessungen`)}
              />
            </FormField>
          </div>
        )}

        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.ist_zertifikat}
            onChange={(e) => {
              const next = { ...draft, ist_zertifikat: e.target.checked };
              setDraft(next);
              onFieldEdit(`positionen[${index}].ist_zertifikat`);
              onPositionChange(next);
            }}
            className="h-4 w-4 rounded border-input"
          />
          <span className="font-medium">Zertifikat / Pauschalposition</span>
          <span className="text-xs text-muted-foreground">
            (z. B. Abnahmeprüfzeugnis)
          </span>
        </label>

        {(position.source_quote || position.source_file) && (
          <div className="mt-3">
            <SourceBadge
              evidence={{
                source_file: position.source_file,
                source_page: position.source_page,
                source_row: position.source_row,
                source_quote: position.source_quote || null,
              }}
              onNavigate={onEvidenceSelect}
            />
          </div>
        )}

      </Accordion.Content>
    </Accordion.Item>
  );
}

