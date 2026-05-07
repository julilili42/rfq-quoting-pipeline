import { Maximize2 } from "lucide-react";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { isApproved } from "@/shared/schemas/approval";

import { useApproval } from "../../hooks/useApproval";
import { useQualityGate } from "../../hooks/useQualityGate";
import type { ReviewDetailContext } from "../../ReviewDetailPage";
import { StepNavigation } from "../../components/StepNavigation";
import { ApprovalPanel } from "./ApprovalPanel";
import { ComparePanes } from "./ComparePanes";
import { FocusToolbar } from "./FocusToolbar";
import { QualityGatePanel } from "./QualityGatePanel";
import { AgentChat } from "./agent/AgentChat";

/**
 * Step 3 — Vergleichen, Anpassen, Quality-Check, Freigeben.
 *
 * Vertical rhythm:
 *
 *   Compare panes (Original ⇆ Angebot)
 *   AgentChat        — natural-language commercial edits
 *   QualityGatePanel — blockers/warnings + stats
 *   ApprovalPanel    — name input + Freigeben (gated by the panel above)
 *
 * The Vollbild variant collapses everything but compare + gate +
 * approval. Hero, KPI strip and step indicator are hidden via the
 * focus mode upstream in ReviewDetailPage. The agent chat is hidden
 * once the review is approved — there's nothing to commercially edit
 * on a finalized angebot.
 */
export function ApprovalStep() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const { detail, focusMode } = useOutletContext<ReviewDetailContext>();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const approval = useApproval(reviewId);
  const gate = useQualityGate(detail);

  if (!reviewId) return null;

  const approved = isApproved(approval.data);
  const firstAttachment = detail.mail.attachments[0]?.name;

  const enterFocus = () => {
    const next = new URLSearchParams(params);
    next.set("focus", "1");
    navigate({ search: next.toString() });
  };

  if (focusMode) {
    return (
      <div className="mx-auto max-w-screen-2xl space-y-6 px-6 py-4">
        <FocusToolbar reviewId={reviewId} fileName={firstAttachment} />
        <ComparePanes
          reviewId={reviewId}
          detail={detail}
          isApproved={approved}
        />
        {!approved && <QualityGatePanel gate={gate} />}
        <ApprovalPanel
          reviewId={reviewId}
          approval={approval.data}
          customerName={detail.anfrage.kunde_firma ?? ""}
          gateAllowsApproval={gate.canApprove}
        />
      </div>
    );
  }

  return (
    <>
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="section-label mb-1">Vergleich</h2>
        </div>
        <Button variant="secondary" size="sm" onClick={enterFocus}>
          <Maximize2 className="h-4 w-4" aria-hidden="true" />
          Vollbild
        </Button>
      </header>

      <ComparePanes
        reviewId={reviewId}
        detail={detail}
        isApproved={approved}
      />

      {!approved && (
        <div className="mt-8">
          <AgentChat
            reviewId={reviewId}
            anfrage={detail.anfrage}
            quotation={detail.quotation}
            overrides={detail.manual_overrides}
          />
        </div>
      )}

      {!approved && (
        <div className="mt-8">
          <h2 className="section-label mb-3">Qualitätsprüfung</h2>
          <QualityGatePanel gate={gate} />
        </div>
      )}

      <div className="mt-8">
        <h2 className="section-label mb-3">Freigabe</h2>
        <ApprovalPanel
          reviewId={reviewId}
          approval={approval.data}
          customerName={detail.anfrage.kunde_firma ?? ""}
          gateAllowsApproval={gate.canApprove}
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
