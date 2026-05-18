import { Checkbox } from "@/shared/components/ui/checkbox";

import type { ReviewStatus, ReviewSummary } from "../schemas/reviewSummary";
import { ReviewCard } from "./ReviewCard";

interface ReviewListProps {
  reviews: ReviewSummary[];
  selectedIds: Set<string>;
  selectionDisabled?: boolean;
  onToggleReview: (reviewId: string) => void;
  onSetReviewsSelected: (reviewIds: string[], selected: boolean) => void;
}

const HEADERS: Array<{ label: string; className: string }> = [
  { label: "",        className: "w-12 px-4 py-3 text-left" },
  { label: "Status",  className: "w-36 px-4 py-3 text-left" },
  { label: "Kunde",   className: "w-48 px-4 py-3 text-left" },
  { label: "Betreff", className: "px-4 py-3 text-left" },
  { label: "Datum",   className: "w-28 px-4 py-3 text-right" },
  { label: "Pos.",    className: "w-16 px-4 py-3 text-right" },
  { label: "Match",   className: "w-20 px-4 py-3 text-right" },
  { label: "Betrag",  className: "w-32 px-4 py-3 text-right" },
  { label: "",        className: "w-36 px-4 py-3" },
];

const GROUPS: Array<{
  title: string;
  statuses: ReviewStatus[];
}> = [
  { title: "Zu prüfen", statuses: ["pdf_bereit"] },
  { title: "In Arbeit", statuses: ["in_arbeit"] },
  { title: "Abgeschlossen", statuses: ["abgeschlossen"] },
];

export function ReviewList({
  reviews,
  selectedIds,
  selectionDisabled = false,
  onToggleReview,
  onSetReviewsSelected,
}: ReviewListProps) {
  if (reviews.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-surface px-4 py-10 text-center text-sm text-muted-foreground">
        Keine Anfragen entsprechen den aktuellen Filtern.
      </p>
    );
  }

  const sections = GROUPS
    .map((group) => ({
      ...group,
      reviews: reviews.filter((review) => group.statuses.includes(review.status)),
    }))
    .filter((group) => group.reviews.length > 0);

  return (
    <div className="space-y-7">
      {sections.map((section) => (
        <section key={section.title} className="space-y-3">
          <h2 className="section-label">{section.title}</h2>

          <ReviewTable
            reviews={section.reviews}
            selectedIds={selectedIds}
            selectionDisabled={selectionDisabled}
            onToggleReview={onToggleReview}
            onSetReviewsSelected={onSetReviewsSelected}
          />
        </section>
      ))}
    </div>
  );
}

function ReviewTable({
  reviews,
  selectedIds,
  selectionDisabled,
  onToggleReview,
  onSetReviewsSelected,
}: {
  reviews: ReviewSummary[];
  selectedIds: Set<string>;
  selectionDisabled: boolean;
  onToggleReview: (reviewId: string) => void;
  onSetReviewsSelected: (reviewIds: string[], selected: boolean) => void;
}) {
  const reviewIds = reviews.map((review) => review.review_id);
  const selectedCount = reviewIds.filter((id) => selectedIds.has(id)).length;
  const allSelected = selectedCount === reviewIds.length;
  const partiallySelected = selectedCount > 0 && !allSelected;

  return (
    <div className="overflow-hidden rounded-xl border border-border shadow-card">
      <div className="overflow-x-auto">
        <table className="min-w-[70rem] w-full table-fixed text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-sunk">
              <th className="w-12 px-4 py-3 text-left">
                <Checkbox
                  checked={allSelected}
                  indeterminate={partiallySelected}
                  disabled={selectionDisabled}
                  ariaLabel={
                    allSelected
                      ? "Gruppe abwählen"
                      : "Alle Anfragen in dieser Gruppe auswählen"
                  }
                  onCheckedChange={() => onSetReviewsSelected(reviewIds, !allSelected)}
                />
              </th>
              {HEADERS.slice(1).map((h) => (
                <th
                  key={h.label}
                  className={`${h.className} text-[11px] font-semibold uppercase tracking-wide text-muted-foreground`}
                >
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {reviews.map((r) => (
              <ReviewCard
                key={r.review_id}
                review={r}
                selected={selectedIds.has(r.review_id)}
                selectionDisabled={selectionDisabled}
                onToggleSelected={() => onToggleReview(r.review_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
