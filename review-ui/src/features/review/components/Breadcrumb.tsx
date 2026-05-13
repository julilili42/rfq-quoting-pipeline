import { Check, ChevronRight, Timer } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/shared/lib/cn";

interface BreadcrumbProps {
  isOutlookReview: boolean;
  reviewId?: string;
  createdAt?: string | null;
  isApproved?: boolean;
  approvedAt?: string | null;
}

function SlaLabel({
  createdAt,
  isApproved,
  approvedAt,
}: {
  createdAt: string;
  isApproved: boolean;
  approvedAt?: string | null;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (isApproved) return undefined;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(interval);
  }, [isApproved]);

  const createdTs = new Date(createdAt).getTime();
  if (Number.isNaN(createdTs)) return null;

  const approvedTs = approvedAt ? new Date(approvedAt).getTime() : Number.NaN;
  const endTs = isApproved && !Number.isNaN(approvedTs) ? approvedTs : now;
  const elapsedMs = Math.max(0, endTs - createdTs);
  const elapsedHours = elapsedMs / (1000 * 60 * 60);
  const label =
    elapsedHours < 1
      ? `${Math.round(elapsedHours * 60)} Min.`
      : `${elapsedHours.toFixed(1).replace(".", ",")} Std.`;
  const tone =
    isApproved
      ? "text-success"
      : elapsedHours < 1
        ? "text-green-600"
        : elapsedHours < 4
          ? "text-yellow-600"
          : "text-red-600";

  return (
    <span
      className={cn("inline-flex items-center gap-1 font-medium", tone)}
      title={
        isApproved
          ? "Stoppuhr gestoppt: Freigabe erteilt"
          : "Reaktionszeit seit Eingang"
      }
    >
      <span className="relative inline-flex h-3.5 w-3.5 items-center justify-center">
        <Timer className="h-3.5 w-3.5" aria-hidden="true" />
        {isApproved && (
          <span className="absolute -right-1 -top-1 inline-flex h-2.5 w-2.5 items-center justify-center rounded-full bg-success text-white ring-1 ring-background">
            <Check className="h-2 w-2" strokeWidth={3} aria-hidden="true" />
          </span>
        )}
      </span>
      {label}
    </span>
  );
}

/**
 * Breadcrumb shown at the top of the review-detail page.
 *
 * Outlook flow:    Anfrage › Pipeline › **Review abc123** · 5 Min.
 * Direct upload:   Direkter Upload › **Review abc123** · 5 Min.
 */
export function Breadcrumb({
  isOutlookReview,
  reviewId,
  createdAt,
  isApproved = false,
  approvedAt = null,
}: BreadcrumbProps) {
  const nodes = isOutlookReview
    ? [
        { label: "Anfrage", active: false },
        { label: "Pipeline", active: false },
        { label: "Review", active: true },
      ]
    : [
        { label: "Direkter Upload", active: false },
        { label: "Review", active: true },
      ];

  return (
    <nav
      aria-label="Breadcrumb"
      className="mb-4 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground"
    >
      {nodes.map((node, i) => (
        <div key={node.label} className="flex items-center gap-1.5">
          <span
            className={cn(
              "flex items-center rounded-full border px-2.5 py-0.5",
              node.active
                ? isApproved
                  ? "border-success/30 bg-success-soft text-success"
                  : "border-brand/30 bg-brand-soft text-brand-dark"
                : "border-border bg-muted text-muted-foreground",
            )}
          >
            {node.label}
            {node.active && reviewId && (
              <code className="ml-1.5 font-mono text-[10px] opacity-75">
                {reviewId}
              </code>
            )}
          </span>
          {i < nodes.length - 1 && (
            <ChevronRight
              className="w-3 h-3 text-muted-foreground/60"
              aria-hidden="true"
            />
          )}
        </div>
      ))}
      {createdAt && (
        <>
          <span className="text-muted-foreground/40">·</span>
          <SlaLabel
            createdAt={createdAt}
            isApproved={isApproved}
            approvedAt={approvedAt}
          />
        </>
      )}
    </nav>
  );
}
