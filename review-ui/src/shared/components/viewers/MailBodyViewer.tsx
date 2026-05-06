import type { MailMeta } from "@/shared/api/reviews";
import { cn } from "@/shared/lib/cn";

interface MailBodyViewerProps {
  mail: MailMeta;
  highlightQuote?: string | null;
  className?: string;
}

export function MailBodyViewer({ mail, highlightQuote, className }: MailBodyViewerProps) {
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
        {highlightQuote
          ? renderWithHighlight(mail.body || "(leerer Body)", highlightQuote)
          : (mail.body || "(leerer Body)")}
      </pre>
    </div>
  );
}

function renderWithHighlight(text: string, query: string) {
  const idx = text.indexOf(query);
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
