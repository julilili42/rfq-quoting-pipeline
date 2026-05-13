import { Download } from "lucide-react";

import { cn } from "@/shared/lib/cn";
import { pdfUrl } from "@/shared/lib/pdfUrl";

import { PdfSourcePreview } from "./PdfSourcePreview";

type PdfKind = "draft" | "final" | "current";

interface PdfViewerProps {
  reviewId: string;
  kind?: PdfKind;
  /**
   * Cache-buster value. Pass a stable value (e.g. `updated_at` from the
   * detail query) so the viewer doesn't refresh on every render — but
   * does refresh whenever the underlying PDF actually changes.
   */
  cacheBuster?: string | number;
  className?: string;
  previewClassName?: string;
}

/**
 * PDF preview pane.
 *
 * Uses the same React PDF viewer as original attachments so both panes
 * keep matching dimensions, zoom behavior and internal scrolling.
 */
export function PdfViewer({
  reviewId,
  kind = "current",
  cacheBuster,
  className,
  previewClassName,
}: PdfViewerProps) {
  const src = pdfUrl(reviewId, kind, cacheBuster);

  const titles: Record<PdfKind, string> = {
    draft: "Angebotsentwurf",
    final: "Finales Angebot",
    current: "Angebot",
  };
  const downloadNames: Record<PdfKind, string> = {
    draft: `Angebotsentwurf_${reviewId}.pdf`,
    final: `Finales_Angebot_${reviewId}.pdf`,
    current: `Angebot_${reviewId}.pdf`,
  };

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border bg-muted px-4 py-2">
        <span className="truncate text-xs font-bold uppercase tracking-wider text-muted-foreground">
          {titles[kind]}
        </span>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
          download={downloadNames[kind]}
        >
          <Download className="h-3 w-3" aria-hidden="true" />
          Download
        </a>
      </header>
      <PdfSourcePreview
        reviewId={reviewId}
        fileName={`${kind}-${reviewId}.pdf`}
        fileUrl={src}
        className={previewClassName}
      />
    </div>
  );
}
