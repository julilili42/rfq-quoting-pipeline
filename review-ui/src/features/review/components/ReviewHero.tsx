import { Pill } from "@/shared/components/ui/pill";

import { Breadcrumb } from "./Breadcrumb";
import { ResetReviewAction } from "./ResetReviewAction";

interface ReviewHeroProps {
  reviewId: string;
  fileName?: string;
  createdAt?: string | null;
  isApproved?: boolean;
  approvedAt?: string | null;
}

export function ReviewHero({
  reviewId,
  fileName,
  createdAt,
  isApproved = false,
  approvedAt = null,
}: ReviewHeroProps) {
  const isOutlookReview = reviewId.length === 12;

  return (
    <header className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <Breadcrumb
          isOutlookReview={isOutlookReview}
          reviewId={reviewId}
          createdAt={createdAt}
          isApproved={isApproved}
          approvedAt={approvedAt}
        />
        <ResetReviewAction reviewId={reviewId} />
      </div>

      <div className="min-w-0">
        <h1 className="text-4xl font-extrabold leading-tight tracking-tight font-display md:text-5xl">
          Angebots-Review<span className="text-brand">.</span>
        </h1>
        <p className="max-w-2xl mt-3 text-base leading-relaxed text-muted-foreground">
          KI-extrahierte Anfrage prüfen, Stammdaten-Treffer validieren und ein
          verkaufsfertiges Angebot erstellen.
        </p>

        {fileName && (
          <div className="flex flex-wrap items-center gap-2 mt-4">
            <Pill tone="neutral">{fileName}</Pill>
          </div>
        )}
      </div>
    </header>
  );
}
