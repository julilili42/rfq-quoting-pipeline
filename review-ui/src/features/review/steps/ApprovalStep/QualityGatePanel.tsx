import { AlertTriangle, ArrowRight, CheckCircle2, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { cn } from "@/shared/lib/cn";

import type { Issue, QualityGateResult } from "../../hooks/useQualityGate";

interface QualityGatePanelProps {
  gate: QualityGateResult;
}

/**
 * Render the pre-approval quality gate.
 *
 * Three visual states:
 *
 *   1. **Blockers present** → red shell, lists blockers, hints at warnings
 *   2. **Only warnings**    → yellow shell, lists warnings, makes clear
 *                              approval is still possible
 *   3. **All clear**        → green confirmation, both lists empty
 */
export function QualityGatePanel({ gate }: QualityGatePanelProps) {
  const hasBlockers = gate.blockers.length > 0;
  const hasWarnings = gate.warnings.length > 0;

  if (!hasBlockers && !hasWarnings) {
    return (
      <section className="flex items-start gap-3 rounded-lg border border-success/30 bg-success-soft p-4">
        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-success" aria-hidden="true" />
        <div className="text-sm">
          <div className="font-display text-base font-bold text-success">
            Bereit zur Freigabe
          </div>
          <p className="mt-0.5 text-success/80">
            Keine offenen Blocker oder Warnungen.{" "}
            {gate.stats.totalPositions > 0 && (
              <>
                Match-Quote {Math.round(gate.stats.matchRate * 100)}% bei{" "}
                {gate.stats.totalPositions} Positionen.
              </>
            )}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className={cn(
        "rounded-lg border bg-surface p-5 shadow-card",
        hasBlockers ? "border-danger/40" : "border-warning/40",
      )}
    >
      <header className="mb-4 flex items-start gap-3">
        {hasBlockers ? (
          <ShieldAlert
            className="mt-0.5 h-5 w-5 flex-shrink-0 text-danger"
            aria-hidden="true"
          />
        ) : (
          <AlertTriangle
            className="mt-0.5 h-5 w-5 flex-shrink-0 text-warning"
            aria-hidden="true"
          />
        )}
        <div>
          <div
            className={cn(
              "font-display text-base font-bold",
              hasBlockers ? "text-danger" : "text-warning",
            )}
          >
            {hasBlockers
              ? `Freigabe blockiert (${gate.blockers.length})`
              : `${gate.warnings.length} ${gate.warnings.length === 1 ? "Warnung" : "Warnungen"}`}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {hasBlockers
              ? "Bitte zuerst alle Blocker beheben."
              : "Freigabe ist möglich, prüfe die Hinweise vor Versand."}
          </p>
        </div>
      </header>

      {hasBlockers && (
        <IssueList title="Blocker" issues={gate.blockers} severity="blocker" />
      )}
      {hasWarnings && (
        <div className={cn(hasBlockers && "mt-4")}>
          <IssueList title="Hinweise" issues={gate.warnings} severity="warning" />
        </div>
      )}
    </section>
  );
}

function IssueList({
  title,
  issues,
  severity,
}: {
  title: string;
  issues: Issue[];
  severity: "blocker" | "warning";
}) {
  return (
    <div>
      <h3 className="section-label mb-2">{title}</h3>
      <ul className="space-y-2">
        {issues.map((issue) => (
          <IssueItem key={issue.id} issue={issue} severity={severity} />
        ))}
      </ul>
    </div>
  );
}

function IssueItem({
  issue,
  severity,
}: {
  issue: Issue;
  severity: "blocker" | "warning";
}) {
  const { reviewId } = useParams<{ reviewId: string }>();
  const target =
    reviewId && issue.step
      ? `/reviews/${encodeURIComponent(reviewId)}/${issue.step}`
      : null;

  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border p-3 text-sm",
        severity === "blocker"
          ? "border-danger/30 bg-danger-soft text-danger"
          : "border-warning/30 bg-warning-soft text-warning",
      )}
    >
      <div className="flex-1">
        <div className="font-semibold">{issue.title}</div>
        <p className="mt-0.5 text-xs opacity-80">{issue.description}</p>
      </div>
      {target && (
        <Link
          to={target}
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-semibold",
            severity === "blocker"
              ? "border-danger/40 bg-surface text-danger hover:bg-danger-soft"
              : "border-warning/40 bg-surface text-warning hover:bg-warning-soft",
          )}
        >
          Beheben
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </Link>
      )}
    </li>
  );
}
