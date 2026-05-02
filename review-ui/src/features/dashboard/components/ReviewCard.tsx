import { ArrowUpRight, FileDown } from "lucide-react";
import { Link } from "react-router-dom";

import { Pill } from "@/shared/components/ui/pill";
import { formatDate, formatEur } from "@/shared/lib/format";
import { pdfUrl } from "@/shared/lib/pdfUrl";

import {
  matchRate,
  type ReviewStatus,
  type ReviewSummary,
} from "../schemas/reviewSummary";

const STATUS_TONE: Record<ReviewStatus, "success" | "info" | "warning"> = {
  abgeschlossen: "success",
  pdf_bereit: "info",
  in_arbeit: "warning",
};

const STATUS_LABEL: Record<ReviewStatus, string> = {
  abgeschlossen: "Abgeschlossen",
  pdf_bereit: "PDF bereit",
  in_arbeit: "In Arbeit",
};

interface ReviewCardProps {
  review: ReviewSummary;
}

export function ReviewCard({ review }: ReviewCardProps) {
  const detailHref = `/reviews/${encodeURIComponent(review.review_id)}`;
  const rate = matchRate(review);

  return (
    <article className="group relative grid grid-cols-[1fr_auto] items-center gap-4 rounded-lg border border-border bg-surface p-4 shadow-card transition-all hover:border-foreground/30 hover:shadow-card-hover">
      <Link
        to={detailHref}
        className="absolute inset-0 z-0 rounded-lg"
        aria-label={`Review ${review.review_id} öffnen`}
      />

      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <Pill tone={STATUS_TONE[review.status]} withDot>
            {STATUS_LABEL[review.status]}
          </Pill>
          {review.matches_no_match > 0 && review.status !== "abgeschlossen" && (
            <Pill tone="danger" withDot>
              {review.matches_no_match}{" "}
              {review.matches_no_match === 1 ? "offen" : "offen"}
            </Pill>
          )}
          <code className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-[10.5px] text-muted-foreground">
            {review.review_id}
          </code>
        </div>

        <div className="truncate text-sm font-semibold text-foreground">
          {review.subject || "(ohne Betreff)"}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
          <span className="truncate max-w-[16rem]">{review.sender || "—"}</span>
          <span aria-hidden="true">·</span>
          <span>{review.positions} Pos</span>
          <span aria-hidden="true">·</span>
          <span>Match {Math.round(rate * 100)}%</span>
          <span aria-hidden="true">·</span>
          <span>{formatEur(review.total_eur)}</span>
          {review.manual_overrides_count > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span>
                {review.manual_overrides_count}{" "}
                {review.manual_overrides_count === 1 ? "Anpassung" : "Anpassungen"}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="relative z-10 flex flex-col items-end gap-1.5">
        <span className="whitespace-nowrap text-[11px] font-semibold text-muted-foreground">
          {formatDate(review.updated_at)}
        </span>
        {review.has_pdf ? (
          <a
            href={pdfUrl(review.review_id, "current", review.updated_at)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[11.5px] font-bold text-white shadow-sm transition-all hover:-translate-y-px hover:bg-brand-dark"
            onClick={(e) => e.stopPropagation()}
          >
            <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
            PDF
          </a>
        ) : (
          <Link
            to={detailHref}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-[11.5px] font-semibold text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
            onClick={(e) => e.stopPropagation()}
          >
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            Öffnen
          </Link>
        )}
      </div>
    </article>
  );
}
