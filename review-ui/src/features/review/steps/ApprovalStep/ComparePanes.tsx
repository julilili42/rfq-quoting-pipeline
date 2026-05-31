import { useEffect, useState, type ReactNode } from "react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { OriginalDocumentViewer } from "@/shared/components/viewers/OriginalDocumentViewer";
import { PdfViewer } from "@/shared/components/viewers/PdfViewer";
import { cn } from "@/shared/lib/cn";

import type { ReviewDetail } from "@/shared/api/reviews";

import { ResizableSplit } from "./ResizableSplit";

interface ComparePanesProps {
  reviewId: string;
  detail: ReviewDetail;
  isApproved: boolean;
  /** Bumped after an on-entry draft rebuild so the iframe reloads the new file. */
  draftPdfVersion?: number;
  focusMode?: boolean;
}

/**
 * Side-by-side comparison view (step 3).
 *
 * Two parallel panes — original (with per-attachment + mail-body tabs) and
 * generated Angebot (Entwurf / Finales Angebot tabs).
 *
 * In fullscreen the panes sit in a {@link ResizableSplit} (draggable divider)
 * and fill the available height via flex — no fixed pixel height — so the view
 * adapts to any screen without overflowing. Outside fullscreen they stack in a
 * responsive grid at their natural height.
 *
 * The PDF tabs hit distinct API URLs (`/pdf/draft` vs `/pdf/final`), which
 * sidesteps the long-standing browser data-URL conflation problem from the
 * Streamlit version.
 */
export function ComparePanes({
  reviewId,
  detail,
  isApproved,
  draftPdfVersion = 0,
  focusMode = false,
}: ComparePanesProps) {
  const attachmentNames = detail.mail.attachments.map((a) => a.name);
  const [offerTab, setOfferTab] = useState<"draft" | "final">("draft");

  // Cache buster lives at the comparison level — when the parent updates
  // `detail` (i.e. after a regenerate or a finalize), both generated PDF
  // viewers refresh in lockstep. draftPdfVersion bumps after an on-entry draft
  // rebuild so the draft iframe reloads the new file.
  const cacheBuster =
    detail.review_id + "::" + (isApproved ? "approved" : "draft") + "::v" + draftPdfVersion;

  useEffect(() => {
    setOfferTab(isApproved ? "final" : "draft");
  }, [isApproved]);

  const fill = focusMode;
  // In fullscreen the viewer outer fills its flex cell (`h-full`) and the PDF
  // preview itself grows inside it (`flex-1`), so there are no magic-number
  // heights. Outside fullscreen the viewers keep their own natural height.
  const viewerClassName = fill ? "h-full" : undefined;
  const previewClassName = fill ? "flex-1 min-h-0" : undefined;
  const tabContentFillCls = fill
    ? "min-h-0 flex-1 data-[state=active]:flex data-[state=active]:flex-col"
    : undefined;

  const original = (
    <ComparePane label="Original" fill={fill}>
      <OriginalDocumentViewer
        reviewId={reviewId}
        mail={detail.mail}
        attachmentNames={attachmentNames}
        fill={fill}
        previewClassName={previewClassName}
      />
    </ComparePane>
  );

  const offer = (
    <ComparePane label="Angebotsentwurf" fill={fill}>
      <Tabs
        value={offerTab}
        onValueChange={(value) => setOfferTab(value as "draft" | "final")}
        className={cn(fill && "flex h-full min-h-0 flex-col")}
      >
        <TabsList className={cn(fill && "shrink-0")}>
          <TabsTrigger value="draft">Entwurf</TabsTrigger>
          {isApproved && <TabsTrigger value="final">Finales Angebot</TabsTrigger>}
        </TabsList>

        <TabsContent value="draft" className={tabContentFillCls}>
          <PdfViewer
            reviewId={reviewId}
            kind="draft"
            cacheBuster={cacheBuster + "::draft"}
            className={viewerClassName}
            previewClassName={previewClassName}
          />
        </TabsContent>

        {isApproved && (
          <TabsContent value="final" className={tabContentFillCls}>
            <PdfViewer
              reviewId={reviewId}
              kind="final"
              cacheBuster={cacheBuster + "::final"}
              className={viewerClassName}
              previewClassName={previewClassName}
            />
          </TabsContent>
        )}
      </Tabs>
    </ComparePane>
  );

  if (focusMode) {
    return <ResizableSplit className="h-full" left={original} right={offer} />;
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      {original}
      {offer}
    </div>
  );
}

interface ComparePaneProps {
  label: string;
  fill?: boolean;
  badge?: ReactNode;
  children: ReactNode;
}

function ComparePane({ label, fill = false, badge, children }: ComparePaneProps) {
  return (
    <section className={cn(fill && "flex h-full min-h-0 flex-col")}>
      <header className={cn("mb-2 flex items-center gap-2", fill && "shrink-0")}>
        <span className="font-display text-lg font-bold tracking-tight text-foreground">
          {label}
        </span>
        {badge}
      </header>
      {fill ? <div className="min-h-0 flex-1">{children}</div> : children}
    </section>
  );
}
