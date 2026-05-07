import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import type { ApprovalRecord } from "@/shared/schemas/approval";
import { isApproved } from "@/shared/schemas/approval";
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
   * Quality-gate verdict. When `false`, the approval button stays
   * disabled regardless of the actor name. The gate panel above
   * already explains *why* — we don't repeat that reasoning here.
   */
  gateAllowsApproval: boolean;
}

function resolveFilenameTemplate(template: string, customerName: string): string {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  return template
    .replace("[Kunde]", customerName || "Kunde")
    .replace("[Datum]", today);
}

export function ApprovalPanel({
  reviewId,
  approval,
  customerName,
  gateAllowsApproval,
}: ApprovalPanelProps) {
  const actor = useReviewUiStore((s) => s.approvalActor);
  const setActor = useReviewUiStore((s) => s.setApprovalActor);
  const changedFields = useReviewUiStore((s) => s.changedFields);

  const finalize = useFinalize(reviewId);
  const transition = useApprovalTransition(reviewId);
  const { data: settings } = useSettings();

  const template = settings?.workflow?.final_pdf_filename_template ?? "Angebot_[Kunde].pdf";
  const defaultFilename = resolveFilenameTemplate(template, customerName);

  const [filename, setFilename] = useState(defaultFilename);

  useEffect(() => {
    setFilename(resolveFilenameTemplate(template, customerName));
  }, [template, customerName]);

  const approved = isApproved(approval);

  if (approved) {
    return (
      <section className="rounded-lg border border-success/30 bg-success-soft p-5">
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

        <div className="mt-5 border-t border-success/20 pt-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
      </section>
    );
  }

  const canApprove = actor.trim().length > 0 && filename.trim().length > 0 && gateAllowsApproval;

  return (
    <section className="rounded-lg border border-border bg-surface p-5 shadow-card">
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Freigegeben durch</Label>
          <Input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Vor- und Nachname"
            autoComplete="name"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Dateiname finale PDF</Label>
          <Input
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            placeholder="Angebot_Kunde.pdf"
          />
        </div>

        <Button
          variant="primary"
          disabled={!canApprove || finalize.isPending}
          title={
            !gateAllowsApproval
              ? "Bitte zuerst die offenen Punkte oben klären."
              : !actor.trim()
                ? "Bitte Namen eintragen."
                : !filename.trim()
                  ? "Bitte Dateinamen eintragen."
                  : undefined
          }
          onClick={() =>
            finalize.mutate(
              { actor: actor.trim(), filename: filename.trim() },
              {
                onSuccess: () => {
                  if (changedFields.size > 0) {
                    transition.mutate({
                      target: "approved",
                      actor: actor.trim(),
                      changed_fields: Array.from(changedFields).sort(),
                      warning_acknowledged: true,
                    });
                  }
                },
              },
            )
          }
        >
          {finalize.isPending ? "Final-PDF wird erzeugt…" : "Freigeben"}
        </Button>

        {finalize.isError && (
          <p className="text-xs text-danger">
            Final-PDF konnte nicht erzeugt werden.
          </p>
        )}
      </div>
    </section>
  );
}
