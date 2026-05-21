import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ShieldAlert,
} from "lucide-react";
import { useState, type ReactNode } from "react";
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

const ISSUE_TARGETS: Record<Issue["step"], { slug: "positions" | "approval"; hash: string }> = {
  customer: { slug: "positions", hash: "customer-data" },
  positions: { slug: "positions", hash: "positions-data" },
  approval: { slug: "approval", hash: "requirements-checklist" },
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
  const showApprovalControls = Boolean(approvalControls) && (isApproved || gate.blockers.length === 0);
  const showSidePanel = showIssues || showApprovalControls;
  const readinessCopy = resolveReadinessCopy(state, isApproved);
  const [expanded, setExpanded] = useState(true);
  const toggleLabel = expanded
    ? "Abschluss & Freigabe einklappen"
    : "Abschluss & Freigabe ausklappen";

  return (
    <section
      aria-labelledby="approval-summary-heading"
      className="overflow-hidden rounded-lg border border-border bg-surface shadow-card"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-surface px-4 py-3">
        <div className="flex min-w-0 items-start gap-3">
          <StatusMark state={state} isApproved={isApproved} />
          <div className="min-w-0">
            <p className="font-display text-lg font-bold tracking-tight text-foreground">
              {readinessCopy.title}
            </p>
            {readinessCopy.description && (
              <p className="mt-0.5 text-sm text-muted-foreground">
                {readinessCopy.description}
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls="approval-summary-content"
            aria-label={toggleLabel}
            title={toggleLabel}
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform",
                expanded && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
        </div>
      </header>

      <div
        id="approval-summary-content"
        className={cn("p-4", !expanded && "hidden")}
      >
        <div
          className={cn(
            "grid gap-4",
            showSidePanel && "xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start",
          )}
        >
          <div className="order-2 min-w-0 space-y-3 xl:order-1">
            {!isApproved && (
              <RequirementsChecklist
                anforderungen={detail.anfrage.anforderungen ?? []}
                acknowledgedIndices={detail.requirements_acknowledged ?? []}
              />
            )}

            <div className="overflow-hidden rounded-md border border-border">
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
              <div className="flex flex-wrap gap-2 text-xs">
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
          </div>

          {showSidePanel && (
            <aside className="order-1 space-y-3 xl:order-2 xl:sticky xl:top-4">
              {showIssues && (
                <IssuesBlock blockers={gate.blockers} warnings={gate.warnings} />
              )}

              {showApprovalControls && approvalControls && (
                isApproved ? (
                  approvalControls
                ) : (
                  <div
                    id="approval-controls"
                    className="scroll-mt-24 overflow-hidden rounded-md border border-border bg-surface"
                  >
                    <div className="bg-muted px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                      Freigabe
                    </div>
                    <div className="p-3">{approvalControls}</div>
                  </div>
                )
              )}
            </aside>
          )}
        </div>
      </div>
    </section>
  );
}

function StatusMark({ state, isApproved }: { state: GateState; isApproved: boolean }) {
  if (isApproved) {
    return (
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-success/25 bg-success-soft text-success">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
      </span>
    );
  }
  if (state === "ok") {
    return (
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted text-success">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
      </span>
    );
  }
  if (state === "warning") {
    return (
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-warning/25 bg-warning-soft text-warning">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-danger/25 bg-danger-soft text-danger">
      <ShieldAlert className="h-4 w-4" aria-hidden="true" />
    </span>
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
      description: "",
    };
  }
  return {
    title: "Versandbereit",
    description: "Keine offenen Blocker oder Empfehlungen gefunden.",
  };
}

function IssuesBlock({ blockers, warnings }: { blockers: Issue[]; warnings: Issue[] }) {
  return (
    <div className="space-y-2">
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
  const target = resolveActionTarget(reviewId, issue.step);
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

function resolveActionTarget(
  reviewId: string | undefined,
  targetStep: Issue["step"] | "approval-controls" | undefined,
) {
  if (!reviewId || !targetStep) return null;
  if (targetStep === "approval-controls") {
    return `/reviews/${encodeURIComponent(reviewId)}/approval#approval-controls`;
  }
  const issueTarget = ISSUE_TARGETS[targetStep];
  return `/reviews/${encodeURIComponent(reviewId)}/${issueTarget.slug}#${issueTarget.hash}`;
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
