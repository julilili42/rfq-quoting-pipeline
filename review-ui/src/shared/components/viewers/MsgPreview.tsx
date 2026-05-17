import { useEffect, useState } from "react";
import MsgReaderImport, { type FieldsData } from "@kenjiuno/msgreader";
import { Loader2, Paperclip } from "lucide-react";

// CJS interop: depending on the bundler, the default export may be wrapped as `{ default }`.
const MsgReader =
  ((MsgReaderImport as unknown) as { default?: typeof MsgReaderImport }).default ??
  MsgReaderImport;

import { cn } from "@/shared/lib/cn";

interface MsgPreviewProps {
  fileUrl: string;
  fileName: string;
  className?: string;
}

interface ParsedMsg {
  subject: string;
  from: string;
  to: string;
  date: string;
  body: string;
  attachments: string[];
}

export function MsgPreview({ fileUrl, fileName, className }: MsgPreviewProps) {
  const [parsed, setParsed] = useState<ParsedMsg | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setParsed(null);
    setError(null);

    fetch(fileUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        const reader = new MsgReader(buffer);
        const data = reader.getFileData();
        if (data.error) throw new Error(data.error);
        setParsed(toParsedMsg(data));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [fileUrl]);

  if (error) {
    return (
      <div className={cn("flex flex-1 items-center justify-center p-12 text-center text-sm text-danger", className)}>
        MSG-Vorschau fehlgeschlagen: {error}
      </div>
    );
  }

  if (!parsed) {
    return (
      <div className={cn("flex flex-1 items-center justify-center gap-2 p-12 text-sm text-muted-foreground", className)}>
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        MSG wird geladen…
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", className)}>
      <header className="space-y-1 border-b border-border bg-gradient-to-b from-muted to-surface px-5 py-4 text-sm">
        <Row label="Betreff" value={parsed.subject || `(${fileName})`} />
        <Row label="Von" value={parsed.from || "—"} />
        {parsed.to && <Row label="An" value={parsed.to} />}
        {parsed.date && <Row label="Datum" value={parsed.date} />}
        {parsed.attachments.length > 0 && (
          <Row
            label="Anhänge"
            value={
              <span className="inline-flex flex-wrap items-center gap-1">
                <Paperclip className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                {parsed.attachments.join(", ")}
              </span>
            }
          />
        )}
      </header>

      <pre className="whitespace-pre-wrap break-words p-5 font-sans text-sm leading-relaxed text-foreground/90">
        {parsed.body || "(leerer Body)"}
      </pre>
    </div>
  );
}

function toParsedMsg(data: FieldsData): ParsedMsg {
  const recipients = (data.recipients ?? [])
    .filter((r) => (r.recipType ?? "to") === "to")
    .map((r) => formatAddress(r.name, r.smtpAddress ?? r.email))
    .filter(Boolean);

  return {
    subject: data.subject ?? data.normalizedSubject ?? "",
    from: formatAddress(data.senderName, data.senderSmtpAddress ?? data.senderEmail),
    to: recipients.join(", "),
    date: data.clientSubmitTime ?? data.messageDeliveryTime ?? data.creationTime ?? "",
    body: (data.body ?? "").replace(/\r\n/g, "\n").trim(),
    attachments: (data.attachments ?? [])
      .map((a) => a.fileName ?? a.fileNameShort ?? a.name ?? "")
      .filter(Boolean),
  };
}

function formatAddress(name?: string, email?: string): string {
  const n = name?.trim();
  const e = email?.trim();
  if (n && e && n !== e) return `${n} <${e}>`;
  return n || e || "";
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-3">
      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
