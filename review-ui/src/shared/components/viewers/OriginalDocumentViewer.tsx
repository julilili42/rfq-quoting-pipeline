import { Download } from "lucide-react";

import { env } from "@/shared/lib/env";
import { cn } from "@/shared/lib/cn";

import { MailBodyViewer } from "./MailBodyViewer";
import { TabularPreview } from "./TabularPreview";
import type { MailMeta } from "@/shared/api/reviews";

interface OriginalDocumentViewerProps {
  reviewId: string;
  mail: MailMeta;
  /** First attachment filename, if any — drives the renderer choice. */
  attachmentName?: string;
  className?: string;
}

const INLINE_RENDERABLE = new Set(["pdf", "png", "jpg", "jpeg"]);
const TABULAR = new Set(["csv", "tsv", "xlsx", "xls"]);

/**
 * Decide-and-render adapter for the "original" pane.
 *
 * Renderer matrix:
 *
 *   ext              renderer
 *   ──────────       ─────────────────────────────────────────
 *   (no attachment)  MailBodyViewer
 *   pdf/png/jpg      iframe → /api/reviews/{id}/original
 *   csv/tsv/xlsx/xls TabularPreview (in-browser parse)
 *   anything else    download-only fallback
 *
 * Tab labels and download links live on this layer so swapping
 * renderers below is purely additive.
 */
export function OriginalDocumentViewer({
  reviewId,
  mail,
  attachmentName,
  className,
}: OriginalDocumentViewerProps) {
  if (!attachmentName) {
    return <MailBodyViewer mail={mail} className={className} />;
  }

  const suffix = (attachmentName ?? "").toLowerCase().split(".").pop() ?? "";
  const downloadUrl = `${env.apiBaseUrl}/api/reviews/${encodeURIComponent(reviewId)}/original`;
  const renderUrl = `${downloadUrl}?v=${Date.now()}`;

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border bg-muted px-4 py-2">
        <span className="truncate text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Original · {attachmentName}
        </span>
        <a
          href={downloadUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
          download={attachmentName}
        >
          <Download className="h-3 w-3" aria-hidden="true" />
          Download
        </a>
      </header>

      {INLINE_RENDERABLE.has(suffix) ? (
        <iframe
          src={renderUrl}
          title={`Original · ${attachmentName}`}
          className="block min-h-[700px] w-full flex-1 border-0 bg-surface"
          loading="lazy"
        />
      ) : TABULAR.has(suffix) ? (
        <TabularPreview reviewId={reviewId} fileName={attachmentName} />
      ) : (
        <div className="flex flex-1 items-center justify-center p-12 text-center text-sm text-muted-foreground">
          Vorschau für <code className="mx-1">{suffix.toUpperCase()}</code>{" "}
          nicht inline verfügbar — bitte herunterladen.
        </div>
      )}
    </div>
  );
}
