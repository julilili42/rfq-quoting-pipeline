import { Check } from "lucide-react";

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

interface ApprovalPanelProps {
  reviewId: string;
  approval: ApprovalRecord | undefined;
  /**
   * Quality-gate verdict. When `false`, the approval button stays
   * disabled regardless of the actor name. The gate panel above
   * already explains *why* — we don't repeat that reasoning here.
   */
  gateAllowsApproval: boolean;
}

/**
 * Approval workflow.
 *
 * Two states:
 *
 * - **Pending**:  name field + "Freigeben" button. Click triggers the
 *                 finalize mutation, which builds the final PDF
 *                 server-side and flips approval state in one call.
 * - **Approved**: shows who approved when, plus a "Zurücknehmen"
 *                 button that flips state back to `reviewed`.
 *
 * The "Freigeben" button has two preconditions:
 *
 *  1. The actor's name has been entered.
 *  2. The quality gate has cleared.
 *
 * Either failing keeps the button disabled.
 */
export function ApprovalPanel({
  reviewId,
  approval,
  gateAllowsApproval,
}: ApprovalPanelProps) {
  const actor = useReviewUiStore((s) => s.approvalActor);
  const setActor = useReviewUiStore((s) => s.setApprovalActor);
  const changedFields = useReviewUiStore((s) => s.changedFields);

  const finalize = useFinalize(reviewId);
  const transition = useApprovalTransition(reviewId);

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

        <div className="mt-4">
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
      </section>
    );
  }

  const canApprove = actor.trim().length > 0 && gateAllowsApproval;

  return (
    <section className="rounded-lg border border-border bg-surface p-5 shadow-card">
      <div className="mb-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Der Angebotsentwurf enthält noch den roten KI-Warnhinweis. Mit der
          Freigabe wird das PDF ohne Warnhinweis neu erzeugt.
        </p>
      </div>

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

        <Button
          variant="primary"
          disabled={!canApprove || finalize.isPending}
          title={
            !gateAllowsApproval
              ? "Bitte zuerst die offenen Punkte oben klären."
              : !actor.trim()
                ? "Bitte Namen eintragen."
                : undefined
          }
          onClick={() =>
            finalize.mutate(actor.trim(), {
              onSuccess: () => {
                // After finalize the backend has already transitioned to
                // `approved`, but we still emit the changed-fields list
                // in case downstream tooling (audit log) wants it.
                if (changedFields.size > 0) {
                  transition.mutate({
                    target: "approved",
                    actor: actor.trim(),
                    changed_fields: Array.from(changedFields).sort(),
                    warning_acknowledged: true,
                  });
                }
              },
            })
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
