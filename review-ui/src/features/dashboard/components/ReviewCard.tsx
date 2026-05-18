import { AlertCircle, ArrowUpRight, FileDown } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "@/shared/lib/cn";
import { formatDate, formatEur } from "@/shared/lib/format";
import { pdfUrl } from "@/shared/lib/pdfUrl";

import { matchRate, type ReviewStatus, type ReviewSummary } from "../schemas/reviewSummary";

const STATUS_CONFIG: Record<
  ReviewStatus,
  { dot: string; text: string; label: string }
> = {
  in_arbeit:     { dot: "bg-warning", text: "text-warning", label: "In Arbeit" },
  pdf_bereit:    { dot: "bg-info",    text: "text-info",    label: "Zu prüfen" },
  abgeschlossen: { dot: "bg-success", text: "text-success", label: "Abgeschlossen" },
};

interface ReviewCardProps {
  review: ReviewSummary;
}

export function ReviewCard({ review }: ReviewCardProps) {
  const detailHref = `/reviews/${encodeURIComponent(review.review_id)}`;
  const cfg = STATUS_CONFIG[review.status];
  const rate = matchRate(review);
  const hasOpenPositions = review.matches_no_match > 0 && review.status !== "abgeschlossen";
  const needsReview = review.status !== "abgeschlossen";

  return (
    <tr className="group border-b border-border last:border-0 transition-colors hover:bg-surface-sunk">
      {/* Status */}
      <td className="w-36 px-4 py-4 align-middle">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", cfg.dot)} aria-hidden="true" />
          <span className={cn("text-xs font-semibold", cfg.text)}>{cfg.label}</span>
        </div>
      </td>

      {/* Kunde */}
      <td className="w-48 px-4 py-4 align-middle">
        <Link
          to={detailHref}
          className="block max-w-[11rem] truncate text-sm font-semibold text-foreground group-hover:text-brand"
          tabIndex={-1}
        >
          {review.sender || "—"}
        </Link>
      </td>

      {/* Betreff + ID */}
      <td className="px-4 py-4 align-middle">
        <Link
          to={detailHref}
          className="block truncate text-sm text-muted-foreground group-hover:text-foreground"
          tabIndex={-1}
        >
          {review.subject || "(ohne Betreff)"}
        </Link>
        <code className="mt-0.5 block font-mono text-[10px] text-muted-foreground/40">
          {review.review_id}
        </code>
      </td>

      {/* Datum */}
      <td className="w-28 px-4 py-4 text-right align-middle">
        <span className="whitespace-nowrap text-xs tabular-nums text-muted-foreground">
          {formatDate(review.updated_at)}
        </span>
      </td>

      {/* Positionen */}
      <td className="w-16 px-4 py-4 text-right align-middle">
        <span className="text-xs tabular-nums text-muted-foreground">{review.positions}</span>
      </td>

      {/* Match-Quote */}
      <td className="w-20 px-4 py-4 text-right align-middle">
        <span
          className={cn(
            "text-xs font-semibold tabular-nums",
            rate >= 0.8 ? "text-success" : rate >= 0.5 ? "text-warning" : "text-brand",
          )}
        >
          {Math.round(rate * 100)}&thinsp;%
        </span>
      </td>

      {/* Betrag */}
      <td className="w-32 px-4 py-4 text-right align-middle">
        <span className="text-sm font-semibold tabular-nums text-foreground">
          {formatEur(review.total_eur)}
        </span>
      </td>

      {/* Aktion + Warnungen */}
      <td className="w-36 px-4 py-4 text-right align-middle">
        <div className="flex items-center justify-end gap-2">
          {hasOpenPositions && (
            <span
              title={`${review.matches_no_match} Position${review.matches_no_match !== 1 ? "en" : ""} ohne Match`}
              className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand"
            >
              <AlertCircle className="h-2.5 w-2.5" aria-hidden="true" />
              {review.matches_no_match}
            </span>
          )}
          {needsReview && (
            <Link
              to={detailHref}
              className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[11px] font-bold text-white shadow-sm transition-all hover:-translate-y-px hover:bg-brand-dark"
            >
              <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
              Review
            </Link>
          )}
          {review.has_pdf && (
            <a
              href={pdfUrl(review.review_id, "current", review.updated_at)}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11px] font-bold transition-all",
                needsReview
                  ? "border border-border bg-surface text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                  : "bg-brand text-white shadow-sm hover:-translate-y-px hover:bg-brand-dark",
              )}
              onClick={(e) => e.stopPropagation()}
              title={needsReview ? "PDF öffnen" : undefined}
            >
              <FileDown className="h-3 w-3" aria-hidden="true" />
              {needsReview ? <span className="sr-only">PDF öffnen</span> : "PDF"}
            </a>
          )}
          {!review.has_pdf && !needsReview && (
            <Link
              to={detailHref}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
            >
              <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
              Öffnen
            </Link>
          )}
        </div>
      </td>
    </tr>
  );
}
