import type { ReviewStatus, ReviewSummary } from "../schemas/reviewSummary";
import { ReviewCard } from "./ReviewCard";

interface ReviewListProps {
  reviews: ReviewSummary[];
}

const HEADERS: Array<{ label: string; className: string }> = [
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

export function ReviewList({ reviews }: ReviewListProps) {
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
          <div className="flex items-center justify-between gap-3">
            <h2 className="section-label">{section.title}</h2>
            <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-semibold tabular-nums text-muted-foreground">
              {section.reviews.length}
            </span>
          </div>

          <ReviewTable reviews={section.reviews} />
        </section>
      ))}
    </div>
  );
}

function ReviewTable({ reviews }: { reviews: ReviewSummary[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-sunk">
              {HEADERS.map((h) => (
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
              <ReviewCard key={r.review_id} review={r} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
