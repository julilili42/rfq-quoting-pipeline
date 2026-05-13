import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/shared/lib/cn";
import type { Evidence } from "@/shared/schemas/anfrage";

interface SourceBadgeProps {
  evidence: Evidence;
  className?: string;
}

export function SourceBadge({
  evidence,
  className,
}: SourceBadgeProps) {
  const [open, setOpen] = useState(false);

  const hasQuote = Boolean(evidence.source_quote);
  const hasLocation = Boolean(
    evidence.source_file ||
    evidence.source_page != null ||
    evidence.source_row != null,
  );

  if (!hasQuote && !hasLocation) return null;

  const locationText = buildLocationText(evidence);

  return (
    <div className={cn("inline-block text-left", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-0.5 rounded text-[11px] font-medium text-muted-foreground hover:text-foreground"
      >
        Quelle
        {open ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </button>

      {open && (
        <div className="mt-1 max-w-xs rounded-md border border-border bg-muted/60 p-2.5 text-xs shadow-sm">
          {locationText && (
            <p className="mb-1.5 font-semibold text-muted-foreground">
              {locationText}
            </p>
          )}
          {evidence.source_quote && (
            <blockquote className="border-l-2 border-border pl-2 italic text-foreground/80 leading-relaxed">
              &ldquo;{evidence.source_quote.slice(0, 200)}
              {evidence.source_quote.length > 200 ? "…" : ""}&rdquo;
            </blockquote>
          )}
        </div>
      )}
    </div>
  );
}

function buildLocationText(ev: Evidence): string {
  const parts: string[] = [];
  if (ev.source_file && ev.source_file !== "mail") parts.push(ev.source_file);
  if (ev.source_page != null) parts.push(`Seite ${ev.source_page}`);
  if (ev.source_row != null) parts.push(`Zeile ${ev.source_row + 1}`);
  return parts.join(" · ");
}
