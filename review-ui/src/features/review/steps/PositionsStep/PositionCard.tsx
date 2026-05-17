import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown, Replace, Trash2 } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Fragment, useEffect, useState } from "react";

import { buttonVariants } from "@/shared/components/ui/button";
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

import {
  CONFIDENCE_EXPLANATION,
  VOLUME_TIERS,
  activeTierIndex,
  articleBadgeTone,
  displayArticleNumber,
} from "../../lib/positionConstants";

import { MatchChip } from "./MatchChip";
import { StammdatenSearchDialog } from "./StammdatenSearchDialog";

function positionsDiffer(a: Position, b: Position): boolean {
  return (Object.keys(a) as (keyof Position)[]).some((key) => {
    const av = a[key], bv = b[key];
    if (Array.isArray(av) && Array.isArray(bv))
      return av.length !== bv.length || av.some((v, i) => v !== bv[i]);
    return av !== bv;
  });
}

interface PositionCardProps {
  reviewId: string;
  position: Position;
  match?: MatchResult;
  quotationItem?: QuotationItem;
  unitPriceOverride?: number;
  discountDisabled?: boolean;
  /** Auto-open the accordion on mount — used right after "add position". */
  defaultOpen?: boolean;
  onPositionChange: (next: Position) => void;
  onUnitPriceChange: (override: ManualOverride | null) => void;
  onDiscountDisabledChange?: (disabled: boolean) => void;
  onFieldEdit: (fieldPath: string) => void;
  onDelete: () => void;
  onEvidenceSelect?: (target: SourceNavigationTarget) => void;
  index: number;
}

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
  discountDisabled = false,
  defaultOpen = false,
  onPositionChange,
  onUnitPriceChange,
  onDiscountDisabledChange,
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
    if (!positionsDiffer(draft, position)) return;
    onFieldEdit(fieldPath);
    onPositionChange(draft);
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
    onFieldEdit(`positionen[${index}].artikelnummer`);
    onPositionChange(updated);
  };

  const handleCustomAssign = (row: StammdatenRow) => {
    const updated: Position = {
      ...draft,
      artikelnummer: row.artikel_nr,
      bezeichnung: row.bezeichnung || draft.bezeichnung,
      werkstoff: row.werkstoff ?? null,
      abmessungen: row.abmessungen ?? null,
      einheit: row.einheit || draft.einheit,
      confidence: "high",
    };
    setDraft(updated);
    setUnitPriceDraft(row.basispreis_eur);
    onFieldEdit(`positionen[${index}].artikelnummer`);
    onFieldEdit(`positionen[${index}].einzelpreis`);
  };

  const initialUnitPrice =
    unitPriceOverride ?? quotationItem?.einzelpreis ?? 0;
  const [unitPriceDraft, setUnitPriceDraft] = useState<number>(initialUnitPrice);
  useEffect(() => setUnitPriceDraft(initialUnitPrice), [initialUnitPrice]);

  const commitUnitPrice = () => {
    if (Math.abs(unitPriceDraft - initialUnitPrice) < 0.005) return;
    onFieldEdit(`positionen[${index}].einzelpreis`);
    onUnitPriceChange({
      target: "pos",
      pos_nr: position.pos_nr,
      mode: "unit_price_eur",
      unit_price_eur: Math.max(0, Number(unitPriceDraft.toFixed(2))),
    });
  };

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const reduceMotion = useReducedMotion();

  const articleNumber = displayArticleNumber(position, match);
  const articleTone = articleBadgeTone(position, match);
  const stammdatenInitialQuery = buildStammdatenSearchQuery(position);
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
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide text-muted-foreground">
              Pos {position.pos_nr}
            </span>
            {position.confidence === "low" && (
              <span
                className="shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                title={CONFIDENCE_EXPLANATION}
              >
                unsichere Extraktion
              </span>
            )}
            <span
              className={cn(
                "max-w-[13rem] shrink-0 truncate rounded-md border px-2 py-1 font-mono text-[13px] font-bold tracking-tight",
                articleTone,
              )}
            >
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
                  initialQuery={stammdatenInitialQuery}
                  initialArticleNumber={position.artikelnummer}
                  initialDescription={position.bezeichnung}
                  initialUnit={position.einheit}
                  initialWerkstoff={position.werkstoff}
                  initialAbmessungen={position.abmessungen}
                  initialUnitPrice={unitPriceDraft || initialUnitPrice}
                  onAssign={handleAssign}
                  onCustomAssign={handleCustomAssign}
                >
                  <motion.button
                    type="button"
                    title="Anderen Artikel zuordnen"
                    className={cn(
                      buttonVariants({ variant: "ghost", size: "sm" }),
                      "group h-7 border border-border bg-surface px-2 text-xs shadow-none hover:border-ek-blue/30 hover:bg-ek-blue-soft hover:text-ek-blue",
                    )}
                    initial={reduceMotion ? false : { opacity: 0, y: -1 }}
                    animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                    whileHover={
                      reduceMotion
                        ? undefined
                        : {
                            y: -0.5,
                            boxShadow: "0 6px 16px hsl(var(--foreground) / 0.07)",
                          }
                    }
                    whileTap={reduceMotion ? undefined : { scale: 0.985 }}
                    transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <Replace
                      className="h-3.5 w-3.5 transition-transform duration-150 group-hover:-rotate-6"
                      aria-hidden="true"
                    />
                    Zuordnen
                  </motion.button>
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
          const showStaffel = !!quotationItem && !draft.ist_zertifikat && tier.rabatt > 0;

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

              {/* Mengenstaffel — nur wenn Mengenrabatt aktiv */}
              {showStaffel && (
                <div className="border-t border-border bg-muted/30 px-4 py-2.5">
                  <div className="flex items-center">
                    {VOLUME_TIERS.map((t, i) => (
                      <Fragment key={t.label}>
                        {i === activeIdx ? (
                          <button
                            type="button"
                            title={discountDisabled ? "Mengenrabatt wieder aktivieren" : "Mengenrabatt deaktivieren"}
                            onClick={() => onDiscountDisabledChange?.(!discountDisabled)}
                            className={cn(
                              "whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-medium transition-all duration-150",
                              discountDisabled
                                ? "bg-muted text-muted-foreground/40 line-through hover:bg-muted/80"
                                : "bg-foreground text-background hover:bg-foreground/85",
                            )}
                          >
                            {t.label}{t.rabatt > 0 && ` –${t.rabatt}%`}
                          </button>
                        ) : (
                          <span className={cn(
                            "whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-medium",
                            i < activeIdx ? "text-muted-foreground/40" : "text-muted-foreground",
                          )}>
                            {t.label}{t.rabatt > 0 && ` –${t.rabatt}%`}
                          </span>
                        )}
                        {i < VOLUME_TIERS.length - 1 && (
                          <div className={cn("h-px min-w-[12px] flex-1", i < activeIdx ? "bg-muted-foreground/20" : "bg-border")} />
                        )}
                      </Fragment>
                    ))}
                  </div>
                  {basis > 0 && !hasOverride && !discountDisabled && (
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      <span className="tabular-nums">{formatEur(basis)}</span>
                      <span className="mx-1.5 text-foreground/30">→</span>
                      <span className="font-medium text-foreground">–{tier.rabatt}% Mengenrabatt</span>
                      <span className="mx-1.5 text-foreground/30">→</span>
                      <span className="font-semibold text-foreground tabular-nums">{formatEur(basis * (1 - tier.rabatt / 100))}/Stk.</span>
                      <span className="ml-3 font-medium text-muted-foreground tabular-nums">–{formatEur(basis * (tier.rabatt / 100))}/Stk.</span>
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

        {/* WEITERE DETAILS — divider-style toggle, hidden for certificate positions */}
        {!draft.ist_zertifikat && (
          <>
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
                <FormField label="Werkstoff">
                  <Input
                    value={draft.werkstoff ?? ""}
                    onChange={(e) => updateField("werkstoff", e.target.value)}
                    onBlur={() => commit(`positionen[${index}].werkstoff`)}
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
          </>
        )}

        <label className="flex items-center gap-2 mt-4 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={draft.ist_zertifikat}
            onChange={(e) => {
              const next = { ...draft, ist_zertifikat: e.target.checked };
              if (e.target.checked) setDetailsOpen(false);
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
    position.abmessungen ?? "",
    position.menge ? String(position.menge) : "",
  ].filter((value) => value.trim().length > 0);
}

function buildStammdatenSearchQuery(position: Position): string {
  const articleNumber = position.artikelnummer.trim();
  if (looksLikeArticleNumber(articleNumber)) return articleNumber;

  return [
    articleNumber,
    position.bezeichnung,
    position.werkstoff ?? "",
    position.abmessungen ?? "",
  ].filter((value) => value.trim().length > 0).join(" ");
}

function looksLikeArticleNumber(value: string): boolean {
  if (!value) return false;
  const compact = value.replace(/\s+/g, "");
  return (
    compact.length >= 6 &&
    /\d/.test(compact) &&
    /^[A-Za-z0-9._/-]+$/.test(compact)
  );
}
