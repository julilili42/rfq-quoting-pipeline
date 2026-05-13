import type { MailMeta } from "@/shared/api/reviews";
import { cn } from "@/shared/lib/cn";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

interface MailBodyViewerProps {
  mail: MailMeta;
  highlightQuote?: string | null;
  sourceTarget?: SourceNavigationTarget | null;
  className?: string;
}

export function MailBodyViewer({
  mail,
  highlightQuote,
  sourceTarget,
  className,
}: MailBodyViewerProps) {
  const body = mail.body || "(leerer Body)";
  const highlightQuery = resolveMailHighlightQuery(body, sourceTarget, highlightQuote);

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card",
        className,
      )}
    >
      <div className="border-b border-border bg-muted px-4 py-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        E-Mail
      </div>

      <header className="space-y-1 border-b border-border bg-gradient-to-b from-muted to-surface px-5 py-4 text-sm">
        <Row label="Betreff" value={mail.subject || "(kein Betreff)"} />
        <Row label="Von" value={mail.from || "—"} />
        {mail.attachments.length > 0 && (
          <Row
            label="Anhänge"
            value={`${mail.attachments.length} ${mail.attachments.length === 1 ? "Datei" : "Dateien"}`}
          />
        )}
      </header>

      <pre className="whitespace-pre-wrap break-words p-5 font-sans text-sm leading-relaxed text-foreground/90">
        {highlightQuery ? renderWithHighlight(body, highlightQuery) : body}
      </pre>
    </div>
  );
}

function renderWithHighlight(text: string, query: string) {
  const idx = text.toLocaleLowerCase("de-DE").indexOf(query.toLocaleLowerCase("de-DE"));
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-amber-200 px-0.5 text-foreground not-italic">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

function resolveMailHighlightQuery(
  text: string,
  sourceTarget?: SourceNavigationTarget | null,
  fallbackQuote?: string | null,
): string | null {
  const candidates = [
    sourceTarget?.evidence.source_quote,
    ...(sourceTarget?.candidates ?? []),
    fallbackQuote,
  ];

  const foldedText = text.toLocaleLowerCase("de-DE");
  for (const candidate of candidates) {
    const cleaned = candidate?.trim();
    if (!cleaned) continue;
    if (foldedText.includes(cleaned.toLocaleLowerCase("de-DE"))) {
      return cleaned;
    }
  }

  return null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-3">
      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
