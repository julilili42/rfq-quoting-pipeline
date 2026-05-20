import { AlertTriangle, ArrowRight, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import type { ReviewDetail } from "@/shared/api/reviews";
import { cn } from "@/shared/lib/cn";
import { formatEur, formatQty } from "@/shared/lib/format";
import type { MatchStatus } from "@/shared/schemas/matchResult";
import type { ManualOverride, QuotationItem } from "@/shared/schemas/quotation";

import type { Issue, QualityGateResult } from "../../hooks/useQualityGate";
import { RequirementsChecklist } from "./RequirementsChecklist";

interface ApprovalSummaryProps {
  detail: ReviewDetail;
  gate: QualityGateResult;
  /**
   * When true, the issues block is hidden — after approval the gate
   * is no longer actionable and the user only needs the price view.
   */
  isApproved: boolean;
  approvalControls?: ReactNode;
}

const MATCH_LABEL: Record<MatchStatus, string> = {
  exact: "Exakt",
  fuzzy: "Fuzzy",
  semantic: "Beschreibung",
  no_match: "Kein Treffer",
};

const ISSUE_TARGETS: Record<Issue["step"], { slug: "positions"; hash: string }> = {
  customer: { slug: "positions", hash: "customer-data" },
  positions: { slug: "positions", hash: "positions-data" },
};

type GateState = "blocked" | "warning" | "ok";

function resolveGateState(gate: QualityGateResult): GateState {
  if (!gate.canApprove) return "blocked";
  if (gate.warnings.length > 0) return "warning";
  return "ok";
}

export function ApprovalSummary({
  detail,
  gate,
  isApproved,
  approvalControls,
}: ApprovalSummaryProps) {
  const quotation = detail.quotation;
  const items = quotation?.items ?? [];
  const matchesByPos = new Map(detail.matches.map((match) => [match.pos_nr, match]));
  const overrides = detail.manual_overrides;
  const priceWarningCount = quotation?.warnungen.length ?? 0;

  const state = resolveGateState(gate);
  const showIssues = !isApproved && (gate.blockers.length > 0 || gate.warnings.length > 0);
  const readinessCopy = resolveReadinessCopy(state, isApproved);

  return (
    <section
      aria-labelledby="approval-summary-heading"
      className="rounded-lg border border-border bg-surface p-4 shadow-card"
    >
      <header className="mb-3">
        <div>
          <p className="font-display text-lg font-bold tracking-tight text-foreground">
            {readinessCopy.title}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {readinessCopy.description}
          </p>
        </div>

      </header>

      {!isApproved && (
        <RequirementsChecklist
          anforderungen={detail.anfrage.anforderungen ?? []}
          acknowledgedIndices={detail.requirements_acknowledged ?? []}
        />
      )}

      {showIssues && (
        <IssuesBlock blockers={gate.blockers} warnings={gate.warnings} />
      )}

      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-muted text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="w-16 px-3 py-1.5">Pos</th>
                <th className="min-w-56 px-3 py-1.5">Artikel</th>
                <th className="px-3 py-1.5 text-right">Menge</th>
                <th className="px-3 py-1.5 text-right">Stückpreis</th>
                <th className="px-3 py-1.5 text-right">Gesamt</th>
                <th className="px-3 py-1.5">Status</th>
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
            <tfoot className="bg-muted/35">
              <tr>
                <td
                  colSpan={4}
                  className="border-t border-border px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Summe
                </td>
                <td className="border-t border-border px-3 py-2.5 text-right font-display text-lg font-bold tabular-nums text-foreground">
                  {formatEur(quotation?.gesamtsumme)}
                </td>
                <td className="border-t border-border px-3 py-2.5" />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {(priceWarningCount > 0 || gate.stats.unmatched > 0) && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {priceWarningCount > 0 && (
            <SummaryPill tone="warning">{priceWarningCount} Preiswarnung(en)</SummaryPill>
          )}
          {gate.stats.unmatched > 0 && (
            <SummaryPill tone="danger">
              {gate.stats.unmatched} Position(en) ohne Treffer
            </SummaryPill>
          )}
        </div>
      )}

      {approvalControls && (
        <div className="mt-4 border-t border-border pt-4">
          {approvalControls}
        </div>
      )}
    </section>
  );
}

function resolveReadinessCopy(state: GateState, isApproved: boolean) {
  if (isApproved) {
    return {
      title: "Freigegeben und versandbereit",
      description: "Finales Angebot und Freigabestatus sind dokumentiert.",
    };
  }
  if (state === "blocked") {
    return {
      title: "Noch nicht versandbereit",
      description: "Bitte zuerst die offenen Probleme beheben oder bewusst als Ausnahme freigeben.",
    };
  }
  if (state === "warning") {
    return {
      title: "Fast versandbereit",
      description: "Es gibt keine Blocker, aber Empfehlungen sollten vor der Freigabe geprüft werden.",
    };
  }
  return {
    title: "Versandbereit",
    description: "Keine offenen Blocker oder Empfehlungen gefunden.",
  };
}

function IssuesBlock({ blockers, warnings }: { blockers: Issue[]; warnings: Issue[] }) {
  return (
    <div className="mt-3 space-y-2">
      {blockers.length > 0 && (
        <IssueGroup
          title={`Probleme (${blockers.length})`}
          issues={blockers}
          severity="blocker"
        />
      )}
      {warnings.length > 0 && (
        <IssueGroup
          title={`Empfehlungen (${warnings.length})`}
          issues={warnings}
          severity="warning"
        />
      )}
    </div>
  );
}

function IssueGroup({
  title,
  issues,
  severity,
}: {
  title: string;
  issues: Issue[];
  severity: "blocker" | "warning";
}) {
  const Icon = severity === "blocker" ? ShieldAlert : AlertTriangle;
  const tone =
    severity === "blocker"
      ? "border-danger/30 bg-danger-soft text-danger"
      : "border-warning/30 bg-warning-soft text-warning";

  return (
    <div className={cn("rounded-md border p-2.5", tone)}>
      <div className="mb-1.5 flex items-center gap-2">
        <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <div className="text-xs font-bold uppercase tracking-wide">{title}</div>
      </div>
      <ul className="space-y-1">
        {issues.map((issue) => (
          <IssueItem key={issue.id} issue={issue} />
        ))}
      </ul>
    </div>
  );
}

function IssueItem({ issue }: { issue: Issue }) {
  const { reviewId } = useParams<{ reviewId: string }>();
  const issueTarget = ISSUE_TARGETS[issue.step];
  const target = reviewId
    ? `/reviews/${encodeURIComponent(reviewId)}/${issueTarget.slug}#${issueTarget.hash}`
    : null;
  return (
    <li className="flex items-start gap-3 rounded-sm bg-surface/60 px-2 py-1 text-sm">
      <div className="flex-1 text-foreground">
        <div className="font-semibold">{issue.title}</div>
        {issue.description && (
          <p className="mt-0.5 text-xs text-muted-foreground">{issue.description}</p>
        )}
      </div>
      {target && (
        <Link
          to={target}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border bg-surface px-2 py-0.5 text-xs font-semibold text-foreground hover:bg-muted"
        >
          Beheben
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </Link>
      )}
    </li>
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
      <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
        {item.pos_nr}
      </td>
      <td className="px-3 py-1.5">
        <div className="font-medium text-foreground">{item.artikel_nr || "—"}</div>
        <div className="max-w-[28rem] truncate text-xs text-muted-foreground">
          {item.bezeichnung}
        </div>
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums">
        {formatQty(item.menge)} {item.einheit}
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums">
        {formatEur(item.einzelpreis)}
      </td>
      <td className="px-3 py-1.5 text-right font-semibold tabular-nums">
        {formatEur(item.gesamtpreis)}
      </td>
      <td className="px-3 py-1.5">
        <div className="flex flex-wrap gap-1.5">
          <SummaryPill tone={matchStatus === "no_match" ? "danger" : "neutral"}>
            {MATCH_LABEL[matchStatus]}
          </SummaryPill>
          {hasOverride && <SummaryPill tone="warning">Preiskorrektur</SummaryPill>}
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
