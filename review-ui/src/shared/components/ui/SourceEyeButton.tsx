import { Eye } from "lucide-react";

import { cn } from "@/shared/lib/cn";
import type { Evidence } from "@/shared/schemas/anfrage";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

interface SourceEyeButtonProps {
  sourceTarget: SourceNavigationTarget;
  onNavigate: (target: SourceNavigationTarget) => void;
  evidence?: Evidence;
  label?: string;
  className?: string;
}

function buildLocationText(ev: Evidence): string {
  const parts: string[] = [];
  if (ev.source_file && ev.source_file !== "mail") parts.push(ev.source_file);
  if (ev.source_page != null) parts.push(`Seite ${ev.source_page}`);
  if (ev.source_row != null) parts.push(`Zeile ${ev.source_row + 1}`);
  return parts.join(" · ");
}

export function SourceEyeButton({
  sourceTarget,
  onNavigate,
  evidence,
  label = "Quelle im Dokument markieren",
  className,
}: SourceEyeButtonProps) {
  const locationText = evidence ? buildLocationText(evidence) : "";
  const hasOverlay = evidence && (evidence.source_quote || locationText);

  return (
    <div className="relative group shrink-0">
      <button
        type="button"
        aria-label={label}
        title={hasOverlay ? undefined : label}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onNavigate(sourceTarget);
        }}
        className={cn(
          "inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors",
          "hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          className,
        )}
      >
        <Eye className="h-3.5 w-3.5" aria-hidden="true" />
      </button>

      {hasOverlay && (
        <div
          className={cn(
            "pointer-events-none absolute bottom-full right-0 z-30 mb-1.5 w-64 rounded-md border border-border bg-surface p-2.5 text-xs shadow-lg",
            "opacity-0 transition-opacity duration-150 group-hover:opacity-100",
          )}
        >
          {locationText && (
            <p className="mb-1.5 font-semibold text-muted-foreground">{locationText}</p>
          )}
          {evidence.source_quote && (
            <blockquote className="pl-2 italic leading-relaxed border-l-2 border-border text-foreground/80">
              &ldquo;{evidence.source_quote.slice(0, 200)}
              {evidence.source_quote.length > 200 ? "…" : ""}&rdquo;
            </blockquote>
          )}
        </div>
      )}
    </div>
  );
}
