import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import { ApiError } from "@/shared/api/client";
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
  const compactEmbedded = embedded && layout === "stacked";

  if (approved) {
    const approvedContent = (
      <div className="flex w-full items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-sm">
          <span className="flex shrink-0 items-center gap-1.5 font-semibold text-success">
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
            Angebot freigegeben
          </span>
          <span className="text-muted-foreground">
            durch <strong className="font-semibold text-foreground">{approval?.approved_by ?? "—"}</strong>
            {" · "}
            {formatDate(approval?.approved_at)}
            {approval?.final_pdf_path && (
              <>
                {" · "}
                <code className="rounded bg-foreground/8 px-1 py-0.5 font-mono text-xs">
                  {approval.final_pdf_path}
                </code>
              </>
            )}
          </span>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            transition.mutate({
              target: "reviewed",
              actor: approval?.approved_by ?? undefined,
            })
          }
          disabled={transition.isPending}
          className="shrink-0"
        >
          Zurücknehmen
        </Button>
      </div>
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
          : compactEmbedded
            ? "space-y-2.5"
            : "space-y-3",
      )}
    >
      <div className={cn("space-y-1.5", compactEmbedded && "space-y-1")}>
        <Label className="text-xs font-semibold text-foreground">
          Freigegeben durch
        </Label>
        <Input
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          placeholder="Vor- und Nachname"
          autoComplete="name"
          className={cn(compactEmbedded && "h-9")}
        />
      </div>

      <div className={cn("space-y-1.5", compactEmbedded && "space-y-1")}>
        <Label className="text-xs font-semibold text-foreground">
          Dateiname finale PDF
        </Label>
        <Input
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          placeholder="Angebot_Kunde.pdf"
          className={cn(compactEmbedded && "h-9")}
        />
      </div>

      <Button
        variant="primary"
        size={compactEmbedded ? "sm" : "md"}
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
        <FinalizeError error={finalize.error} embedded={embedded} />
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

/**
 * Finalize can be rejected server-side even when the client gate looked
 * clean (the two gates are independent implementations). When that
 * happens the server returns its own quality gate in the 409 body — we
 * surface its blockers verbatim instead of a generic error so the user
 * knows exactly what to fix.
 */
function FinalizeError({ error, embedded }: { error: unknown; embedded?: boolean }) {
  const serverBlockers = extractServerBlockers(error);
  return (
    <div
      className={cn(
        "rounded-md border border-danger/40 bg-danger-soft p-2.5 text-xs text-foreground",
        embedded && "lg:col-span-3",
      )}
      role="alert"
    >
      {serverBlockers.length > 0 ? (
        <>
          <strong>Freigabe vom Server abgelehnt:</strong>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {serverBlockers.map((title) => (
              <li key={title}>{title}</li>
            ))}
          </ul>
        </>
      ) : (
        <span>Final-PDF konnte nicht erzeugt werden. Bitte erneut versuchen.</span>
      )}
    </div>
  );
}

function extractServerBlockers(error: unknown): string[] {
  if (!(error instanceof ApiError) || error.status !== 409) return [];
  const body = error.body as
    | { detail?: { quality_gate?: { blockers?: Array<{ title?: string }> } } }
    | undefined;
  const blockers = body?.detail?.quality_gate?.blockers ?? [];
  return blockers.map((b) => b.title ?? "").filter((title) => title.length > 0);
}
