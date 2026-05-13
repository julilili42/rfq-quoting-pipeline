import { AlertTriangle, FileCheck2, ShieldCheck } from "lucide-react";

import type { ReviewDetail } from "@/shared/api/reviews";
import { cn } from "@/shared/lib/cn";
import { formatEur, formatPercent, formatQty } from "@/shared/lib/format";
import type { MatchStatus } from "@/shared/schemas/matchResult";
import type { ManualOverride, QuotationItem } from "@/shared/schemas/quotation";

import type { QualityGateResult } from "../../hooks/useQualityGate";

interface ApprovalSummaryProps {
  detail: ReviewDetail;
  gate: QualityGateResult;
}

const MATCH_LABEL: Record<MatchStatus, string> = {
  exact: "Exakt",
  fuzzy: "Fuzzy",
  semantic: "Semantisch",
  no_match: "Kein Treffer",
};

export function ApprovalSummary({ detail, gate }: ApprovalSummaryProps) {
  const quotation = detail.quotation;
  const items = quotation?.items ?? [];
  const matchesByPos = new Map(detail.matches.map((match) => [match.pos_nr, match]));
  const overrides = detail.manual_overrides;
  const pdfState = detail.has_final_pdf
    ? "Final bereit"
    : detail.has_draft_pdf
      ? "Entwurf bereit"
      : "Offen";
  const warningCount = quotation?.warnungen.length ?? 0;

  return (
    <section
      aria-labelledby="approval-summary-heading"
      className="rounded-lg border border-border bg-surface p-5 shadow-card"
    >
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="approval-summary-heading" className="section-label mb-2">
            Abschluss-Check
          </h2>
          <p className="text-sm font-medium text-foreground">
            Preis- und Dokumentenüberblick vor der Freigabe
          </p>
        </div>
        <div
          className={cn(
            "inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-xs font-semibold",
            gate.canApprove
              ? "bg-success-soft text-success"
              : "bg-danger-soft text-danger",
          )}
        >
          {gate.canApprove ? (
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {gate.canApprove ? "Freigabefähig" : "Blockiert"}
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-y border-border py-3 text-sm md:grid-cols-5">
        <SummaryStat label="Summe" value={formatEur(quotation?.gesamtsumme)} strong />
        <SummaryStat label="Positionen" value={`${items.length}/${gate.stats.totalPositions}`} />
        <SummaryStat label="Match" value={formatPercent(gate.stats.matchRate)} />
        <SummaryStat label="Manuell" value={overrides.length} />
        <SummaryStat label="PDF" value={pdfState} icon={<FileCheck2 className="h-3.5 w-3.5" />} />
      </dl>

      <div className="mt-4 overflow-hidden rounded-md border border-border">
        <div className="max-h-72 overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-muted text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="w-16 px-3 py-2">Pos</th>
                <th className="min-w-56 px-3 py-2">Artikel</th>
                <th className="px-3 py-2 text-right">Menge</th>
                <th className="px-3 py-2 text-right">Stückpreis</th>
                <th className="px-3 py-2 text-right">Gesamt</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface">
              {items.length > 0 ? (
                items.map((item) => (
                  <SummaryRow
                    key={`${item.pos_nr}-${item.artikel_nr}`}
                    item={item}
                    matchStatus={matchesByPos.get(item.pos_nr)?.status ?? "no_match"}
                    hasOverride={hasManualOverride(item, overrides)}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-sm text-muted-foreground">
                    Keine Preispositionen vorhanden.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {(warningCount > 0 || gate.stats.unmatched > 0 || overrides.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {warningCount > 0 && (
            <SummaryPill tone="warning">{warningCount} Preiswarnung(en)</SummaryPill>
          )}
          {gate.stats.unmatched > 0 && (
            <SummaryPill tone="danger">
              {gate.stats.unmatched} Position(en) ohne Treffer
            </SummaryPill>
          )}
          {overrides.length > 0 && (
            <SummaryPill tone="neutral">
              {overrides.length} manuelle Eingriff(e)
            </SummaryPill>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryStat({
  label,
  value,
  icon,
  strong = false,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 flex min-w-0 items-center gap-1.5 truncate font-display tracking-tight",
          strong ? "text-lg font-bold" : "text-base font-semibold",
        )}
      >
        {icon}
        <span className="truncate">{value}</span>
      </dd>
    </div>
  );
}

function SummaryRow({
  item,
  matchStatus,
  hasOverride,
}: {
  item: QuotationItem;
  matchStatus: MatchStatus;
  hasOverride: boolean;
}) {
  return (
    <tr>
      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
        {item.pos_nr}
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-foreground">{item.artikel_nr || "—"}</div>
        <div className="max-w-[28rem] truncate text-xs text-muted-foreground">
          {item.bezeichnung}
        </div>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {formatQty(item.menge)} {item.einheit}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {formatEur(item.einzelpreis)}
      </td>
      <td className="px-3 py-2 text-right font-semibold tabular-nums">
        {formatEur(item.gesamtpreis)}
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1.5">
          <SummaryPill tone={matchStatus === "no_match" ? "danger" : "neutral"}>
            {MATCH_LABEL[matchStatus]}
          </SummaryPill>
          {hasOverride && <SummaryPill tone="warning">Manuell</SummaryPill>}
        </div>
      </td>
    </tr>
  );
}

function SummaryPill({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "neutral" | "warning" | "danger";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold",
        tone === "neutral" && "bg-muted text-muted-foreground",
        tone === "warning" && "bg-warning-soft text-warning",
        tone === "danger" && "bg-danger-soft text-danger",
      )}
    >
      {children}
    </span>
  );
}

function hasManualOverride(item: QuotationItem, overrides: ManualOverride[]): boolean {
  return overrides.some((override) => {
    if (override.target === "pos") return override.pos_nr === item.pos_nr;
    return override.artikel_nr === item.artikel_nr;
  });
}
