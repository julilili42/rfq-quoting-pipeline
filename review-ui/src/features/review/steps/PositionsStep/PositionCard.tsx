import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown, Replace, Trash2 } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { FormField } from "@/shared/components/ui/FormField";
import { Input } from "@/shared/components/ui/input";
import { SourceEyeButton } from "@/shared/components/ui/SourceEyeButton";
import { cn } from "@/shared/lib/cn";
import { formatEur } from "@/shared/lib/format";
import type { Position } from "@/shared/schemas/anfrage";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";
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
  onEvidenceSelect?: (target: SourceNavigationTarget) => void;
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

const CONFIDENCE_EXPLANATION =
  "Farbe zeigt die KI-Selbsteinschätzung der Extraktion: grün eindeutig, gelb abgeleitet/teilweise lesbar, rot unklar. Kein objektiver Prüfscore.";

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

  const articleNumber = position.artikelnummer || "Unbekannt";
  const quantityMeta = `${Math.round(position.menge)} ${position.einheit}`;
  const sourceEvidence = {
    source_file: position.source_file,
    source_page: position.source_page,
    source_row: position.source_row,
    source_quote: position.source_quote || null,
  };
  const positionSourceTarget: SourceNavigationTarget = {
    evidence: sourceEvidence,
    targetKind: "position",
    candidates: buildPositionSourceCandidates(position),
    label: `Position ${position.pos_nr}`,
  };
  const canNavigateToSource =
    Boolean(onEvidenceSelect) &&
    Boolean(
      sourceEvidence.source_file ||
        sourceEvidence.source_page != null ||
        sourceEvidence.source_quote,
    );

  return (
    <Accordion.Item
      value={`pos-${position.pos_nr}`}
      className={cn(
        "rounded-lg border bg-surface shadow-card transition-colors [&[data-state=open]>h3]:border-b [&[data-state=open]>h3]:border-border",
        confirmingDelete ? "border-danger/40" : "border-border hover:border-foreground/20",
      )}
    >
      <Accordion.Header className="flex items-stretch">
        <Accordion.Trigger
          className={cn(
            "group flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left text-sm font-semibold",
          )}
        >
          <span className="flex min-w-0 flex-1 items-center gap-2">
            <span
              className={cn(
                "group relative shrink-0 rounded px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide",
                position.confidence === "high" && "bg-success/10 text-success",
                position.confidence === "medium" && "bg-warning/10 text-warning",
                position.confidence === "low" && "bg-danger/10 text-danger",
              )}
              title={CONFIDENCE_EXPLANATION}
            >
              Pos {position.pos_nr}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute bottom-full left-0 z-30 mb-1.5 w-72 rounded-md border border-border bg-surface p-2.5 text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground/80 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100"
              >
                {CONFIDENCE_EXPLANATION}
              </span>
            </span>
            <span className="max-w-[13rem] shrink-0 truncate rounded-md border border-border bg-muted px-2 py-1 font-mono text-[13px] font-bold tracking-tight text-foreground">
              {articleNumber}
            </span>
            <span className="min-w-0 truncate text-sm font-semibold text-foreground">
              {position.bezeichnung || "Keine Bezeichnung"}
            </span>
            <span className="shrink-0 text-xs font-medium text-muted-foreground">
              {quantityMeta}
            </span>
          </span>
          <ChevronDown
            className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
            aria-hidden="true"
          />
        </Accordion.Trigger>

        {canNavigateToSource && onEvidenceSelect && (
          <div className="flex items-center px-1.5">
            <SourceEyeButton
              sourceTarget={positionSourceTarget}
              onNavigate={onEvidenceSelect}
              evidence={sourceEvidence}
              label={`Quelle für Position ${position.pos_nr} markieren`}
            />
          </div>
        )}

        {/* Delete — always visible, separate click target */}
        {confirmingDelete ? (
          <div className="flex items-center gap-1.5 border-l border-l-danger/20 bg-danger-soft px-3">
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
            className="flex items-center border-l border-border px-3 text-muted-foreground transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </Accordion.Header>

      <Accordion.Content
        className="px-4 pb-4 pt-3 data-[state=closed]:hidden"
        forceMount={defaultOpen ? true : undefined}
      >
        {/* Primary matching status */}
        <div className="mb-4">
          {match ? (
            <MatchChip
              match={match}
              extractedArticleNumber={position.artikelnummer}
              action={
                <StammdatenSearchDialog
                  reviewId={reviewId}
                  posNr={position.pos_nr}
                  initialQuery={position.artikelnummer || position.bezeichnung}
                  onAssign={handleAssign}
                >
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    title="Anderen Artikel zuordnen"
                    className="h-7 border border-border bg-surface px-2 text-xs"
                  >
                    <Replace className="h-3.5 w-3.5" aria-hidden="true" />
                    Zuordnen
                  </Button>
                </StammdatenSearchDialog>
              }
            />
          ) : (
            <span />
          )}
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
            <div className="overflow-hidden border rounded-xl border-border">
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
                      className="flex-1 h-auto min-w-0 p-0 text-xl font-bold bg-transparent border-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    />
                    <Input
                      value={draft.einheit}
                      onChange={(e) => updateField("einheit", e.target.value)}
                      onBlur={() => commit(`positionen[${index}].einheit`)}
                      className="h-auto p-0 text-sm font-semibold bg-transparent border-0 shadow-none w-14 shrink-0 text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-1 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Lieferung</p>
                  <Input
                    value={draft.lieferzeit ?? ""}
                    onChange={(e) => updateField("lieferzeit", e.target.value)}
                    onBlur={() => commit(`positionen[${index}].lieferzeit`)}
                    className="h-auto p-0 text-xl font-bold bg-transparent border-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    placeholder="z. B. 6 Wo."
                  />
                  <Input
                    value={draft.lieferwerk ?? ""}
                    onChange={(e) => updateField("lieferwerk", e.target.value)}
                    onBlur={() => commit(`positionen[${index}].lieferwerk`)}
                    className="h-auto p-0 text-xs font-medium bg-transparent border-0 shadow-none text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
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
                    className="h-auto p-0 text-xl font-bold bg-transparent border-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
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
          className="flex items-center w-full gap-3 mt-5 text-xs transition-colors text-muted-foreground hover:text-foreground"
        >
          <div className="flex-1 h-px bg-border" />
          <span className="flex items-center gap-1 font-medium shrink-0">
            <ChevronDown
              className={cn("h-3 w-3 transition-transform duration-200", detailsOpen && "rotate-180")}
              aria-hidden="true"
            />
            Weitere Details
          </span>
          <div className="flex-1 h-px bg-border" />
        </button>

        {detailsOpen && (
          <div className="grid grid-cols-1 mt-3 gap-x-4 gap-y-3 md:grid-cols-2">
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

        <label className="flex items-center gap-2 mt-4 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={draft.ist_zertifikat}
            onChange={(e) => {
              const next = { ...draft, ist_zertifikat: e.target.checked };
              setDraft(next);
              onFieldEdit(`positionen[${index}].ist_zertifikat`);
              onPositionChange(next);
            }}
            className="w-4 h-4 rounded border-input"
          />
          <span className="font-medium">Zertifikat / Pauschalposition</span>
          <span className="text-xs text-muted-foreground">
            (z. B. Abnahmeprüfzeugnis)
          </span>
        </label>

      </Accordion.Content>
    </Accordion.Item>
  );
}

function buildPositionSourceCandidates(position: Position): string[] {
  return [
    position.artikelnummer,
    String(position.pos_nr),
    position.bezeichnung,
    position.zeichnungsnummer ?? "",
    position.abmessungen ?? "",
    position.menge ? String(position.menge) : "",
  ].filter((value) => value.trim().length > 0);
}
