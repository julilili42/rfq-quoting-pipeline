import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { OriginalDocumentViewer } from "@/shared/components/viewers/OriginalDocumentViewer";
import { PdfViewer } from "@/shared/components/viewers/PdfViewer";

import type { ReviewDetail } from "@/shared/api/reviews";
import { Pill } from "@/shared/components/ui/pill";

interface ComparePanesProps {
  reviewId: string;
  detail: ReviewDetail;
  isApproved: boolean;
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
export function ComparePanes({ reviewId, detail, isApproved }: ComparePanesProps) {
  const attachmentNames = detail.mail.attachments.map((a) => a.name);

  // Cache buster lives at the comparison level — when the parent
  // updates `detail` (i.e. after a regenerate or a finalize), both
  // PDF iframes refresh in lockstep.
  const cacheBuster = detail.review_id + "::" + (isApproved ? "approved" : "draft");

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <ComparePane label="Original">
        <OriginalDocumentViewer
          reviewId={reviewId}
          mail={detail.mail}
          attachmentNames={attachmentNames}
        />
      </ComparePane>

      <ComparePane
        label="Angebotsentwurf"
        badge={isApproved ? <Pill tone="success" withDot>freigegeben</Pill> : null}
      >
        <Tabs defaultValue="draft">
          <TabsList>
            <TabsTrigger value="draft">Entwurf</TabsTrigger>
            {isApproved && <TabsTrigger value="final">Finales Angebot</TabsTrigger>}
          </TabsList>

          <TabsContent value="draft">
            <PdfViewer
              reviewId={reviewId}
              kind="draft"
              cacheBuster={cacheBuster + "::draft"}
            />
          </TabsContent>

          {isApproved && (
            <TabsContent value="final">
              <PdfViewer
                reviewId={reviewId}
                kind="final"
                cacheBuster={cacheBuster + "::final"}
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
  badge?: React.ReactNode;
  children: React.ReactNode;
}

function ComparePane({ label, badge, children }: ComparePaneProps) {
  return (
    <section>
      <header className="mb-2 flex items-center gap-2">
        <span className="section-label">{label}</span>
        {badge}
      </header>
      {children}
    </section>
  );
}
