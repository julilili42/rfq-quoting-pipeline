import { Maximize2 } from "lucide-react";
import { useHotkeys } from "react-hotkeys-hook";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";
import { isApproved } from "@/shared/schemas/approval";

import { useApproval } from "../../hooks/useApproval";
import { useQualityGate } from "../../hooks/useQualityGate";
import type { ReviewDetailContext } from "../../ReviewDetailPage";
import { StepNavigation } from "../../components/StepNavigation";
import { ApprovalPanel } from "./ApprovalPanel";
import { ApprovalSummary } from "./ApprovalSummary";
import { ComparePanes } from "./ComparePanes";
import { FocusToolbar } from "./FocusToolbar";

/**
 * Step 2 — Vergleichen, Anpassen, Abschluss-Check, Freigeben.
 *
 * Vertical rhythm:
 *
 *   Compare panes (Original ⇆ Angebot)
 *   ApprovalSummary  — gate + stats + positions table (one card)
 *   ApprovalPanel    — name input + Freigeben (gated by the summary)
 *
 * Hero, KPI strip and step indicator are hidden via the focus mode
 * upstream in ReviewDetailPage.
 */
export function ApprovalStep() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const { detail, focusMode } = useOutletContext<ReviewDetailContext>();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const approval = useApproval(reviewId);
  const gate = useQualityGate(detail);

  const enterFocus = () => {
    const next = new URLSearchParams(params);
    next.set("focus", "1");
    navigate({ search: next.toString() });
  };

  useHotkeys("alt+f", enterFocus, { enabled: !focusMode, preventDefault: true });

  if (!reviewId) return null;

  const approved = isApproved(approval.data);
  const firstAttachment = detail.mail.attachments[0]?.name;

  if (focusMode) {
    return (
      <div className="mx-auto max-w-screen-2xl space-y-6 px-6 py-4">
        <FocusToolbar reviewId={reviewId} fileName={firstAttachment} />
        <ComparePanes
          reviewId={reviewId}
          detail={detail}
          isApproved={approved}
          focusMode
        />
        <ApprovalSummary detail={detail} gate={gate} isApproved={approved} />
        <ApprovalPanel
          reviewId={reviewId}
          approval={approval.data}
          customerName={detail.anfrage.kunde_firma ?? ""}
          blockerCount={gate.blockers.length}
          warningCount={gate.warnings.length}
        />
      </div>
    );
  }

  return (
    <>
      <header className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <div className="group relative">
          <Button variant="secondary" size="sm" onClick={enterFocus}>
            <Maximize2 className="h-4 w-4" aria-hidden="true" />
            Vollbild
          </Button>
          <ShortcutHint keys={["Alt", "F"]} />
        </div>
      </header>

      <ComparePanes
        reviewId={reviewId}
        detail={detail}
        isApproved={approved}
      />

      <div className="mt-8">
        <ApprovalSummary detail={detail} gate={gate} isApproved={approved} />
      </div>

      <div className="mt-8">
        <h2 className="section-label mb-3">Freigabe</h2>
        <ApprovalPanel
          reviewId={reviewId}
          approval={approval.data}
          customerName={detail.anfrage.kunde_firma ?? ""}
          blockerCount={gate.blockers.length}
          warningCount={gate.warnings.length}
        />
      </div>

      <StepNavigation
        current="approval"
        onFinish={() => navigate("/")}
        finishLabel="Fertig — zurück zur Übersicht"
      />
    </>
  );
}
