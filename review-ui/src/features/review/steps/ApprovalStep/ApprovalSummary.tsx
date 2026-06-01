import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  MessageSquarePlus,
  ShieldAlert,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { StammdatenDetailDialog } from "@/features/stammdaten/components/StammdatenDetailDialog";
import type { ReviewDetail } from "@/shared/api/reviews";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { cn } from "@/shared/lib/cn";
import { formatEur, formatQty } from "@/shared/lib/format";
import type { MatchStatus } from "@/shared/schemas/matchResult";
import type { ManualOverride, QuotationItem } from "@/shared/schemas/quotation";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

import type { Issue, QualityGateResult } from "../../hooks/useQualityGate";
import { useEscalateReview } from "../../hooks/useReviewMutations";
import { useStammdatenSearch } from "../../hooks/useStammdaten";
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
  const [clarificationOpen, setClarificationOpen] = useState(false);
  const [clarificationReason, setClarificationReason] = useState("");
  const [selectedArticleNr, setSelectedArticleNr] = useState<string | null>(null);
  const selectedArticle = useStammdatenSearch(
    selectedArticleNr ?? "",
    Boolean(selectedArticleNr),
  );
  const selectedArticleRow = findStammdatenRow(
    selectedArticle.data,
    selectedArticleNr,
  );
  const escalation = useEscalateReview(detail.review_id);
  const manualClarificationActive = Boolean(detail.escalation?.escalated);
  const showManualClarification = !isApproved || manualClarificationActive;
  const toggleLabel = expanded
    ? "Anforderungen & Freigabe einklappen"
    : "Anforderungen & Freigabe ausklappen";

  const closeClarificationEditor = () => {
    setClarificationOpen(false);
    setClarificationReason("");
  };

  const submitClarification = () => {
    const reason = clarificationReason.trim();
    if (!reason) return;
    escalation.mutate(
      { reason },
      {
        onSuccess: closeClarificationEditor,
      },
    );
  };

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
        <div className="flex shrink-0 items-center gap-2">
          {showManualClarification && (
            <ManualClarificationHeaderAction
              active={manualClarificationActive}
              open={clarificationOpen}
              reason={detail.escalation?.reason}
              clearing={escalation.isPending}
              onOpenChange={setClarificationOpen}
              onClear={() => escalation.mutate(null)}
            />
          )}
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

      {manualClarificationActive && detail.escalation && (
        <div className="border-b border-warning/25 bg-warning-soft/60 px-4 py-2.5">
          <div className="flex min-w-0 items-start gap-2 text-sm">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
            <div className="min-w-0">
              <span className="font-semibold text-warning">
                Manuelle Klärung erforderlich:
              </span>{" "}
              <span className="text-foreground">{detail.escalation.reason}</span>
            </div>
          </div>
        </div>
      )}

      <ManualClarificationDialog
        open={clarificationOpen && !manualClarificationActive}
        reviewId={detail.review_id}
        reason={clarificationReason}
        pending={escalation.isPending}
        onOpenChange={setClarificationOpen}
        onReasonChange={setClarificationReason}
        onCancel={closeClarificationEditor}
        onSubmit={submitClarification}
      />

      <div
        id="approval-summary-content"
        className={cn("p-4", !expanded && "hidden")}
      >
          <div
            className={cn(
            "grid gap-x-4 gap-y-3",
            showSidePanel && "xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start",
          )}
        >
          <div className="order-2 min-w-0 space-y-3 xl:contents">
            {!isApproved && (
              <div className={cn("xl:col-start-1 xl:row-start-1", !showIssues && "xl:self-stretch xl:flex xl:flex-col")}>
                <RequirementsChecklist
                  anforderungen={detail.anfrage.anforderungen ?? []}
                  acknowledgedIndices={detail.requirements_acknowledged ?? []}
                  mailAttachments={detail.mail_attachments}
                />
              </div>
            )}

            <div className="overflow-hidden rounded-md border border-border xl:col-span-2 xl:col-start-1 xl:row-start-2">
              <div className="overflow-x-auto">
                <table className="w-full table-fixed text-left text-sm">
                  <colgroup>
                    <col className="w-16" />
                    <col className="w-44" />
                    <col />
                    <col className="w-28" />
                    <col className="w-32" />
                    <col className="w-36" />
                    <col className="w-24" />
                  </colgroup>
                  <thead className="sticky top-0 bg-muted text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-1.5">Pos</th>
                      <th className="px-3 py-1.5">Artikel-Nr.</th>
                      <th className="px-3 py-1.5">Bezeichnung</th>
                      <th className="whitespace-nowrap px-3 py-1.5 text-right">Menge</th>
                      <th className="whitespace-nowrap px-3 py-1.5 text-right">Stückpreis</th>
                      <th className="whitespace-nowrap px-3 py-1.5 text-right">Gesamt</th>
                      <th className="whitespace-nowrap px-3 py-1.5">Status</th>
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
                          onArticleClick={setSelectedArticleNr}
                        />
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} className="px-3 py-4 text-sm text-muted-foreground">
                          Keine Preispositionen vorhanden.
                        </td>
                      </tr>
                    )}
                  </tbody>
                  <tfoot className="bg-muted/35">
                    <tr>
                      <td
                        colSpan={5}
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
              <div className="flex flex-wrap gap-2 text-xs xl:col-span-2 xl:col-start-1 xl:row-start-3">
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
            <aside
              className={cn(
                "order-1 space-y-3",
                isApproved
                  ? "xl:col-span-2 xl:col-start-1 xl:row-start-1"
                  : "xl:col-start-2 xl:row-start-1 xl:self-stretch xl:sticky xl:top-4",
              )}
            >
              {showIssues && (
                <IssuesBlock blockers={gate.blockers} warnings={gate.warnings} />
              )}

              {showApprovalControls && approvalControls && (
                isApproved ? (
                  approvalControls
                ) : (
                  <div
                    id="approval-controls"
                    className={cn(
                      "scroll-mt-24 overflow-hidden rounded-md border border-border bg-surface",
                      !showIssues && "xl:h-full",
                    )}
                  >
                    <div className="bg-muted px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                      Freigabe
                    </div>
                    <div className="p-2.5">{approvalControls}</div>
                  </div>
                )
              )}
            </aside>
          )}
        </div>
      </div>

      {selectedArticleRow && (
        <StammdatenDetailDialog
          row={selectedArticleRow}
          onClose={() => setSelectedArticleNr(null)}
        />
      )}
    </section>
  );
}

function ManualClarificationHeaderAction({
  active,
  open,
  reason,
  clearing,
  onOpenChange,
  onClear,
}: {
  active: boolean;
  open: boolean;
  reason?: string;
  clearing?: boolean;
  onOpenChange: (open: boolean) => void;
  onClear: () => void;
}) {
  if (active) {
    return (
      <div className="hidden items-center gap-1 sm:flex">
        <span
          className="max-w-[16rem] truncate rounded-full border border-warning/30 bg-warning-soft px-2.5 py-1 text-xs font-semibold text-warning"
          title={reason}
        >
          Klärung aktiv
        </span>
        <button
          type="button"
          disabled={clearing}
          onClick={onClear}
          title="Klärung entfernen"
          className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-surface text-muted-foreground transition-colors hover:border-danger/40 hover:bg-danger-soft hover:text-danger disabled:opacity-50"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      className={cn(
        "text-muted-foreground shadow-sm hover:border-foreground/30 hover:bg-muted hover:text-foreground",
        open && "border-ring/50 bg-muted text-foreground ring-2 ring-ring/20",
      )}
      onClick={() => onOpenChange(!open)}
    >
      <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
      {open ? "Ticket offen" : "Klärung anlegen"}
    </Button>
  );
}

function ManualClarificationDialog({
  open,
  reviewId,
  reason,
  pending,
  onOpenChange,
  onReasonChange,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  reviewId: string;
  reason: string;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onReasonChange: (reason: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl overflow-hidden p-0">
        <DialogHeader className="border-b border-border bg-surface-sunk px-5 py-4">
          <DialogTitle>Manuelle Klärung anlegen</DialogTitle>
          <DialogDescription>
            Ein internes Ticket für Punkte, die vor der Freigabe außerhalb des normalen Reviews geklärt werden müssen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-5 py-4">
          <div className="overflow-hidden rounded-md border border-border">
            <div className="bg-muted px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              Ticket
            </div>
            <div className="grid grid-cols-1 divide-y divide-border text-sm sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              <TicketMeta label="Status" value="Offen" />
              <TicketMeta label="Typ" value="Review-Klärung" />
              <TicketMeta label="Review" value={reviewId} mono />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label
              htmlFor={`manual-clarification-${reviewId}`}
              className="text-xs font-semibold text-foreground"
            >
              Klärungsgrund
            </Label>
            <textarea
              id={`manual-clarification-${reviewId}`}
              className="flex min-h-[124px] w-full resize-none rounded-md border border-input bg-surface px-3 py-2 text-sm leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={reason}
              onChange={(event) => onReasonChange(event.target.value)}
              autoFocus
              placeholder="z. B. Zeichnung prüfen, Verpackungsdaten nachfragen oder Werkskalkulation erforderlich"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-border bg-surface-sunk px-5 py-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={onCancel}
          >
            Abbrechen
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!reason.trim() || pending}
            onClick={onSubmit}
          >
            Angebot markieren
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TicketMeta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0 px-3 py-2.5">
      <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={cn(
          "mt-0.5 truncate text-xs font-semibold text-foreground",
          mono && "font-mono",
        )}
        title={value}
      >
        {value}
      </p>
    </div>
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
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-ek-blue/25 bg-ek-blue-soft text-ek-blue">
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
          title="Probleme"
          issues={blockers}
          severity="blocker"
        />
      )}
      {warnings.length > 0 && (
        <IssueGroup
          title="Empfehlungen"
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
    <div className={cn("rounded-md border p-2", tone)}>
      <div className="mb-1.5 flex items-center gap-2 px-0.5">
        <Icon className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
        <div className="text-[11px] font-bold uppercase tracking-wide">{title}</div>
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
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-sm bg-surface/70 px-2 py-1.5">
      <div className="min-w-0">
        <div
          className="truncate text-xs font-semibold leading-snug text-foreground"
          title={issue.description ? `${issue.title} - ${issue.description}` : issue.title}
        >
          {issue.title}
        </div>
      </div>
      {target && (
        <Link
          to={target}
          className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-surface px-2 text-[11px] font-semibold text-foreground hover:bg-muted"
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
  onArticleClick,
}: {
  item: QuotationItem;
  matchStatus: MatchStatus;
  hasOverride: boolean;
  onArticleClick: (artikelNr: string) => void;
}) {
  const articleNr = item.artikel_nr.trim();
  const clickable = articleNr.length > 0;
  return (
    <tr
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      aria-label={clickable ? `Artikel ${articleNr} öffnen` : undefined}
      onClick={clickable ? () => onArticleClick(articleNr) : undefined}
      onKeyDown={(event) => {
        if (!clickable || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        onArticleClick(articleNr);
      }}
      className={cn(
        clickable &&
          "group cursor-pointer transition-all duration-150 hover:bg-ek-blue-soft/35 hover:shadow-[inset_3px_0_0_hsl(var(--ek-blue))] focus-visible:bg-ek-blue-soft/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
      )}
    >
      <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
        {item.pos_nr}
      </td>
      <td className="px-3 py-1.5">
        {articleNr ? (
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs font-semibold text-foreground transition-colors group-hover:bg-brand-soft group-hover:text-brand">
            {articleNr}
          </span>
        ) : (
          <span className="font-medium text-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-1.5">
        <div className="max-w-[32rem] truncate text-xs text-muted-foreground">
          {item.bezeichnung || "—"}
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
        {formatQty(item.menge)} {item.einheit}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
        {formatEur(item.einzelpreis)}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 text-right font-semibold tabular-nums">
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

function findStammdatenRow(
  rows: StammdatenRow[] | undefined,
  artikelNr: string | null,
): StammdatenRow | null {
  if (!rows || !artikelNr) return null;
  const normalized = normalizeArticleNr(artikelNr);
  return (
    rows.find((row) => normalizeArticleNr(row.artikel_nr) === normalized) ??
    rows[0] ??
    null
  );
}

function normalizeArticleNr(value: string): string {
  return value.trim().toLocaleLowerCase("de-DE");
}
