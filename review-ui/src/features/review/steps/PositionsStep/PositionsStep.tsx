import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";

import { OriginalDocumentViewer } from "@/shared/components/viewers/OriginalDocumentViewer";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

import type { ReviewDetailContext } from "../../ReviewDetailPage";
import { StepNavigation } from "../../components/StepNavigation";
import { PositionsEditor } from "./PositionsEditor";

export function PositionsStep() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const { detail } = useOutletContext<ReviewDetailContext>();
  const [activeSource, setActiveSource] = useState<SourceNavigationTarget | null>(null);

  if (!reviewId) return null;

  const attachmentNames = detail.mail.attachments.map((a) => a.name);

  return (
    <>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="order-2 lg:order-1">
          <OriginalDocumentViewer
            reviewId={reviewId}
            mail={detail.mail}
            attachmentNames={attachmentNames}
            activeSource={activeSource}
            className="lg:sticky lg:top-6"
          />
        </div>

        <div className="order-1 lg:order-2">
          <PositionsEditor
            reviewId={reviewId}
            anfrage={detail.anfrage}
            matches={detail.matches}
            quotation={detail.quotation}
            overrides={detail.manual_overrides}
            onEvidenceSelect={setActiveSource}
          />
        </div>
      </div>

      <StepNavigation current="positions" forwardLabel="Positionen bestätigen" />
    </>
  );
}
