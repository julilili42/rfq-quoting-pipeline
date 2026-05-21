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
 * Step 2 — Abschluss & Freigabe, danach Dokumentvergleich.
 *
 * Vertical rhythm:
 *
 *   ApprovalSummary  — readiness, open issues, positions table + approval controls
 *   Compare panes (Original ⇆ Angebot)
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
  const approvalControls = (
    <ApprovalPanel
      reviewId={reviewId}
      approval={approval.data}
      customerName={detail.anfrage.kunde_firma ?? ""}
      blockerCount={gate.blockers.length}
      warningCount={gate.warnings.length}
      embedded
      layout="stacked"
    />
  );

  if (focusMode) {
    return (
      <div className="mx-auto max-w-screen-2xl space-y-6 px-6 py-4">
        <FocusToolbar reviewId={reviewId} fileName={firstAttachment} />
        <DecisionSectionHeading />
        <ApprovalSummary
          detail={detail}
          gate={gate}
          isApproved={approved}
          approvalControls={approvalControls}
        />
        <ComparePanes
          reviewId={reviewId}
          detail={detail}
          isApproved={approved}
          focusMode
        />
      </div>
    );
  }

  return (
    <>
      <DecisionSectionHeading />
      <ApprovalSummary
        detail={detail}
        gate={gate}
        isApproved={approved}
        approvalControls={approvalControls}
      />

      <div className="mt-8">
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-label">Dokumentvergleich</h2>
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
      </div>

      <StepNavigation
        current="approval"
        onFinish={() => navigate("/")}
        finishLabel="Fertig — zurück zur Übersicht"
      />
    </>
  );
}

function DecisionSectionHeading() {
  return (
    <div className="mb-3">
      <h2 id="approval-summary-heading" className="section-label">
        Abschluss &amp; Freigabe
      </h2>
    </div>
  );
}
