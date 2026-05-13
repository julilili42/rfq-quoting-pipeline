import { useEffect, useState, type ReactNode } from "react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { OriginalDocumentViewer } from "@/shared/components/viewers/OriginalDocumentViewer";
import { PdfViewer } from "@/shared/components/viewers/PdfViewer";

import type { ReviewDetail } from "@/shared/api/reviews";

interface ComparePanesProps {
  reviewId: string;
  detail: ReviewDetail;
  isApproved: boolean;
  focusMode?: boolean;
}

/**
 * Side-by-side comparison view (step 3).
 *
 * Two parallel panes — original (with per-attachment + mail-body tabs) and
 * generated Angebot (Entwurf / Finales Angebot tabs).
 *
 * The PDF tabs hit distinct API URLs (`/pdf/draft` vs `/pdf/final`),
 * which sidesteps the long-standing browser data-URL conflation
 * problem from the Streamlit version.
 */
export function ComparePanes({
  reviewId,
  detail,
  isApproved,
  focusMode = false,
}: ComparePanesProps) {
  const attachmentNames = detail.mail.attachments.map((a) => a.name);
  const [offerTab, setOfferTab] = useState<"draft" | "final">("draft");

  // Cache buster lives at the comparison level — when the parent
  // updates `detail` (i.e. after a regenerate or a finalize), both
  // generated PDF viewers refresh in lockstep.
  const cacheBuster =
    detail.review_id + "::" + (isApproved ? "approved" : "draft");
  const previewClassName = focusMode
    ? "h-[calc(100vh-14rem)] min-h-[720px]"
    : undefined;

  useEffect(() => {
    setOfferTab(isApproved ? "final" : "draft");
  }, [isApproved]);

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <ComparePane label="Original">
        <OriginalDocumentViewer
          reviewId={reviewId}
          mail={detail.mail}
          attachmentNames={attachmentNames}
          previewClassName={previewClassName}
        />
      </ComparePane>

      <ComparePane label="Angebotsentwurf">
        <Tabs
          value={offerTab}
          onValueChange={(value) => setOfferTab(value as "draft" | "final")}
        >
          <TabsList>
            <TabsTrigger value="draft">Entwurf</TabsTrigger>
            {isApproved && (
              <TabsTrigger value="final">Finales Angebot</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="draft">
            <PdfViewer
              reviewId={reviewId}
              kind="draft"
              cacheBuster={cacheBuster + "::draft"}
              previewClassName={previewClassName}
            />
          </TabsContent>

          {isApproved && (
            <TabsContent value="final">
              <PdfViewer
                reviewId={reviewId}
                kind="final"
                cacheBuster={cacheBuster + "::final"}
                previewClassName={previewClassName}
              />
            </TabsContent>
          )}
        </Tabs>
      </ComparePane>
    </div>
  );
}

interface ComparePaneProps {
  label: string;
  badge?: ReactNode;
  children: ReactNode;
}

function ComparePane({ label, badge, children }: ComparePaneProps) {
  return (
    <section>
      <header className="flex items-center gap-2 mb-2">
        <span className="font-display text-lg font-bold tracking-tight text-foreground">
          {label}
        </span>
        {badge}
      </header>
      {children}
    </section>
  );
}
