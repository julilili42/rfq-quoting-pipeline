import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import type { ApprovalRecord } from "@/shared/schemas/approval";
import { isApproved } from "@/shared/schemas/approval";
import { cn } from "@/shared/lib/cn";
import { formatDate } from "@/shared/lib/format";

import {
  useApprovalTransition,
} from "../../hooks/useApproval";
import { useFinalize } from "../../hooks/useReviewMutations";
import { useSettings } from "@/features/settings/hooks/useSettings";

interface ApprovalPanelProps {
  reviewId: string;
  approval: ApprovalRecord | undefined;
  customerName: string;
  /**
   * Open issues from the quality gate. Both blockers and warnings can
   * be acknowledged and overridden via the same checkbox — the visual
   * tone escalates when blockers are present so the user notices.
   */
  blockerCount: number;
  warningCount: number;
  embedded?: boolean;
  layout?: "inline" | "stacked";
}

function resolveFilenameTemplate(template: string, customerName: string): string {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  return template
    .replace("[Kunde]", customerName || "Kunde")
    .replace("[Datum]", today)
    .replace(/ /g, "_");
}

export function ApprovalPanel({
  reviewId,
  approval,
  customerName,
  blockerCount,
  warningCount,
  embedded = false,
  layout = embedded ? "inline" : "stacked",
}: ApprovalPanelProps) {
  const hasBlockers = blockerCount > 0;
  const hasWarnings = warningCount > 0;
  const actor = useReviewUiStore((s) => s.approvalActor);
  const setActor = useReviewUiStore((s) => s.setApprovalActor);
  const changedFields = useReviewUiStore((s) => s.changedFields);

  const finalize = useFinalize(reviewId);
  const transition = useApprovalTransition(reviewId);
  const { data: settings } = useSettings();

  const template = settings?.workflow?.final_pdf_filename_template ?? "Angebot_[Kunde].pdf";
  const defaultFilename = resolveFilenameTemplate(template, customerName);

  const [filename, setFilename] = useState(defaultFilename);
  const [warningsAck, setWarningsAck] = useState(false);
  const [exceptionReason, setExceptionReason] = useState("");

  useEffect(() => {
    setFilename(resolveFilenameTemplate(template, customerName));
  }, [template, customerName]);

  useEffect(() => {
    if (!hasWarnings) {
      setWarningsAck(false);
      setExceptionReason("");
    }
  }, [hasWarnings]);

  const approved = isApproved(approval);

  if (approved) {
    const approvedContent = (
      <>
        <div className="mb-3 flex items-center gap-2 text-success">
          <Check className="h-5 w-5" aria-hidden="true" />
          <span className="font-display text-base font-bold">
            Angebot freigegeben
          </span>
        </div>
        <p className="text-sm text-foreground/80">
          Freigegeben durch{" "}
          <strong>{approval?.approved_by ?? "—"}</strong> am{" "}
          <strong>{formatDate(approval?.approved_at)}</strong>.
          {approval?.final_pdf_path && (
            <>
              {" "}Finales PDF (ohne KI-Warnhinweis):{" "}
              <code className="rounded bg-foreground/5 px-1.5 py-0.5 font-mono text-xs">
                {approval.final_pdf_path}
              </code>
            </>
          )}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() =>
              transition.mutate({
                target: "reviewed",
                actor: approval?.approved_by ?? undefined,
              })
            }
            disabled={transition.isPending}
          >
            Freigabe zurücknehmen
          </Button>
        </div>

        <div className="mt-4 border-t border-success/20 pt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Systemintegration
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled
              title="SAP-Integration — in Vorbereitung"
              className="flex cursor-not-allowed items-center gap-3.5 rounded-xl border border-border bg-white px-4 py-3 text-left opacity-60 shadow-sm"
            >
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#003366]">
                <span className="text-[11px] font-black tracking-widest text-white">SAP</span>
              </div>
              <div>
                <p className="text-sm font-semibold leading-tight text-foreground">In SAP anlegen</p>
                <p className="mt-0.5 text-[11px] leading-tight text-muted-foreground">Demnächst verfügbar</p>
              </div>
            </button>

            <button
              type="button"
              disabled
              title="Salesforce-Integration — in Vorbereitung"
              className="flex cursor-not-allowed items-center gap-3.5 rounded-xl border border-border bg-white px-4 py-3 text-left opacity-60 shadow-sm"
            >
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#0176D3]">
                <svg viewBox="0 0 24 24" className="h-5 w-5 fill-white" aria-hidden="true">
                  <path d="M10 4a4 4 0 0 1 3.9 3.1A3.5 3.5 0 0 1 17.5 11a3.5 3.5 0 0 1-.5 6.5H7A4 4 0 0 1 7 10a4 4 0 0 1 .4 0A4 4 0 0 1 10 4z"/>
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold leading-tight text-foreground">In Salesforce erstellen</p>
                <p className="mt-0.5 text-[11px] leading-tight text-muted-foreground">Demnächst verfügbar</p>
              </div>
            </button>
          </div>
        </div>
      </>
    );

    if (embedded) {
      return (
        <div className="rounded-md border border-success/30 bg-success-soft p-3">
          {approvedContent}
        </div>
      );
    }

    return (
      <section className="rounded-lg border border-success/30 bg-success-soft p-5">
        {approvedContent}
      </section>
    );
  }

  const warningsHandled = !hasWarnings || warningsAck;
  const canApprove =
    actor.trim().length > 0 &&
    filename.trim().length > 0 &&
    !hasBlockers &&
    warningsHandled;

  const form = (
    <div
      className={cn(
        embedded && layout === "inline"
          ? "grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end"
          : "space-y-3",
      )}
    >
      <div className="space-y-1.5">
        <Label className="text-xs font-semibold text-foreground">
          Freigegeben durch
        </Label>
        <Input
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          placeholder="Vor- und Nachname"
          autoComplete="name"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs font-semibold text-foreground">
          Dateiname finale PDF
        </Label>
        <Input
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          placeholder="Angebot_Kunde.pdf"
        />
      </div>

      <Button
        variant="primary"
        className={embedded && layout === "inline" ? "w-full lg:w-auto" : "w-full"}
        disabled={!canApprove || finalize.isPending}
        title={
          !actor.trim()
            ? "Bitte Namen eintragen."
            : !filename.trim()
              ? "Bitte Dateinamen eintragen."
              : hasBlockers
                ? `${blockerCount} Blocker müssen behoben werden (z.B. 0,00-€-Positionen oder fehlende Stammdaten-Treffer).`
                : !warningsHandled
                  ? "Bitte Empfehlungen bestätigen."
                  : undefined
        }
        onClick={() => {
          const trimmedReason = exceptionReason.trim();
          finalize.mutate(
            {
              actor: actor.trim(),
              filename: filename.trim(),
              warning_acknowledged: hasWarnings ? warningsAck : false,
              ...(trimmedReason ? { exception_reason: trimmedReason } : {}),
            },
            {
              onSuccess: () => {
                if (changedFields.size > 0) {
                  transition.mutate(
                    {
                      target: "approved",
                      actor: actor.trim(),
                      changed_fields: Array.from(changedFields).sort(),
                      warning_acknowledged: hasWarnings ? warningsAck : false,
                      ...(trimmedReason ? { exception_reason: trimmedReason } : {}),
                    },
                    { onError: () => {} },
                  );
                }
              },
            },
          );
        }}
      >
        {finalize.isPending ? "Final-PDF wird erzeugt…" : "Freigeben"}
      </Button>

      {hasBlockers && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-md border border-danger/40 bg-danger-soft p-2.5 text-xs text-foreground",
            embedded && "lg:col-span-3",
          )}
          role="alert"
        >
          <span aria-hidden="true" className="mt-0.5 text-danger">⛔</span>
          <span>
            <strong>Freigabe gesperrt:</strong> {blockerCount}{" "}
            {blockerCount === 1 ? "Blocker" : "Blocker"} müssen behoben werden,
            bevor das Angebot rausgehen kann. Siehe Liste oben.
          </span>
        </div>
      )}

      {hasWarnings && (
        <>
          <label
            className={cn(
              "flex items-start gap-2 rounded-md border border-warning/30 bg-warning-soft p-2.5 text-xs",
              embedded && "lg:col-span-3",
            )}
          >
            <input
              className="mt-0.5 h-4 w-4 cursor-pointer accent-warning"
              type="checkbox"
              checked={warningsAck}
              onChange={(e) => setWarningsAck(e.target.checked)}
            />
            <span className="text-foreground">
              Empfehlungen geprüft und akzeptiert.
            </span>
          </label>

          <div className={cn("space-y-1.5", embedded && "lg:col-span-3")}>
            <Label className="text-xs font-semibold text-foreground">
              Grund für Ausnahme (optional)
            </Label>
            <textarea
              className="flex min-h-[68px] w-full rounded-md border border-input bg-surface px-3 py-2 text-sm leading-relaxed ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={exceptionReason}
              onChange={(e) => setExceptionReason(e.target.value)}
              placeholder="Kurze Notiz für die Freigabehistorie"
            />
          </div>
        </>
      )}

      {finalize.isError && (
        <p className={cn("text-xs text-danger", embedded && "lg:col-span-3")}>
          Final-PDF konnte nicht erzeugt werden.
        </p>
      )}
      {transition.isError && (
        <p className={cn("text-xs text-danger", embedded && "lg:col-span-3")}>
          Freigabe-Status konnte nicht gesetzt werden.
        </p>
      )}
    </div>
  );

  if (embedded) {
    return form;
  }

  return (
    <section className="rounded-lg border border-border bg-surface p-5 shadow-card">
      {form}
    </section>
  );
}
