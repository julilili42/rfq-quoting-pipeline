import { useEffect, useState } from "react";
import { Download } from "lucide-react";

import { env } from "@/shared/lib/env";
import { cn } from "@/shared/lib/cn";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import type { Evidence } from "@/shared/schemas/anfrage";

import { MailBodyViewer } from "./MailBodyViewer";
import { PdfSourcePreview } from "./PdfSourcePreview";
import { TabularPreview } from "./TabularPreview";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";
import type { MailMeta } from "@/shared/api/reviews";

interface OriginalDocumentViewerProps {
  reviewId: string;
  mail: MailMeta;
  attachmentNames?: string[];
  activeSource?: SourceNavigationTarget | null;
  className?: string;
  previewClassName?: string;
  /** Fill the parent's height (fullscreen compare) instead of natural height. */
  fill?: boolean;
}

const INLINE_RENDERABLE = new Set(["png", "jpg", "jpeg"]);
const TABULAR = new Set(["csv", "tsv", "xlsx", "xls"]);

export function OriginalDocumentViewer({
  reviewId,
  mail,
  attachmentNames = [],
  activeSource,
  className,
  previewClassName,
  fill = false,
}: OriginalDocumentViewerProps) {
  const defaultTab = attachmentNames.length > 0 ? attachmentNames[0] : "mail";
  const [activeTab, setActiveTab] = useState(defaultTab);
  const activeEvidence = activeSource?.evidence ?? null;
  const activeSourceFile = resolveSourceAttachmentName(
    activeSource,
    attachmentNames,
    mail,
  );

  useEffect(() => {
    if (!activeSource) return;
    setActiveTab(activeSourceFile ?? "mail");
  }, [activeSource, activeSourceFile]);

  return (
    <div className={cn("flex flex-col", fill && "h-full min-h-0", className)}>
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className={cn(fill && "flex min-h-0 flex-1 flex-col")}
      >
        <TabsList className={cn(fill && "shrink-0")}>
          {attachmentNames.map((name) => (
            <TabsTrigger key={name} value={name}>
              <span className="max-w-[160px] truncate">{name}</span>
            </TabsTrigger>
          ))}
          <TabsTrigger value="mail">E-Mail</TabsTrigger>
        </TabsList>

        {attachmentNames.map((name) => {
          const suffix = name.toLowerCase().split(".").pop() ?? "";
          const url = `${env.apiBaseUrl}/api/reviews/${encodeURIComponent(reviewId)}/attachment/${encodeURIComponent(name)}`;

          const isActive = activeTab === name;
          const evidenceForThisFile =
            isActive && activeSourceFile === name
              ? activeEvidence
              : null;
          const sourceForThisFile =
            isActive && activeSourceFile === name
              ? activeSource
              : null;

          // Include page fragment when evidence points to a specific page.
          // Using a key that includes the page forces the iframe to reload
          // and jump to that page.
          const sourcePage = evidenceForThisFile?.source_page ?? null;
          const renderUrl = `${url}?v=${sourcePage ?? 0}${sourcePage ? `#page=${sourcePage}` : ""}`;
          const iframeKey = `${name}-p${sourcePage ?? 0}`;

          return (
            <TabsContent
              key={name}
              value={name}
              className={cn(
                fill &&
                  "min-h-0 flex-1 data-[state=active]:flex data-[state=active]:flex-col",
              )}
            >
              <div
                className={cn(
                  "flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card",
                  fill && "h-full min-h-0",
                )}
              >
                <header className="flex items-center justify-between gap-2 border-b border-border bg-muted px-4 py-2">
                  <span className="truncate text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    {name}
                  </span>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
                    download={name}
                  >
                    <Download className="h-3 w-3" aria-hidden="true" />
                    Download
                  </a>
                </header>

                {suffix === "pdf" ? (
                  <PdfSourcePreview
                    reviewId={reviewId}
                    fileName={name}
                    fileUrl={url}
                    sourceTarget={sourceForThisFile}
                    className={previewClassName}
                  />
                ) : INLINE_RENDERABLE.has(suffix) ? (
                  <iframe
                    key={iframeKey}
                    src={renderUrl}
                    title={`Original · ${name}`}
                    className={cn(
                      "block min-h-[700px] w-full flex-1 border-0 bg-surface",
                      previewClassName,
                    )}
                    loading="lazy"
                  />
                ) : TABULAR.has(suffix) ? (
                  <TabularPreview
                    reviewId={reviewId}
                    fileName={name}
                    highlightRow={evidenceForThisFile?.source_row ?? null}
                  />
                ) : (
                  <div className="flex flex-1 items-center justify-center p-12 text-center text-sm text-muted-foreground">
                    Vorschau für{" "}
                    <code className="mx-1">{suffix.toUpperCase()}</code> nicht
                    inline verfügbar — bitte herunterladen.
                  </div>
                )}
              </div>
            </TabsContent>
          );
        })}

        <TabsContent
          value="mail"
          className={cn(
            fill &&
              "min-h-0 flex-1 data-[state=active]:flex data-[state=active]:flex-col",
          )}
        >
          <MailBodyViewer
            mail={mail}
            className={cn(fill && "h-full min-h-0")}
            sourceTarget={activeSourceFile ? null : activeSource}
            highlightQuote={
              !activeSourceFile &&
              (activeEvidence?.source_file === "mail" ||
                !activeEvidence?.source_file)
                ? (activeEvidence?.source_quote ?? null)
                : null
            }
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function resolveSourceAttachmentName(
  source: SourceNavigationTarget | null | undefined,
  attachmentNames: string[],
  mail: MailMeta,
): string | null {
  const evidence = source?.evidence;
  const direct = resolveAttachmentName(evidence?.source_file, attachmentNames, evidence);
  if (direct) return direct;

  const pdfAttachment = attachmentNames.find((name) => name.toLowerCase().endsWith(".pdf"));
  if (
    source?.targetKind === "position" &&
    pdfAttachment &&
    !mailContainsQuote(mail, source.evidence.source_quote)
  ) {
    return pdfAttachment;
  }

  return null;
}

function resolveAttachmentName(
  sourceFile: string | null | undefined,
  attachmentNames: string[],
  evidence?: Evidence | null,
): string | null {
  if (sourceFile === "mail") return null;
  if (!sourceFile) {
    if (attachmentNames.length === 1 && evidence?.source_page != null) {
      return attachmentNames[0];
    }
    return null;
  }

  const direct = attachmentNames.find((name) => name === sourceFile);
  if (direct) return direct;

  const folded = sourceFile.toLowerCase();
  const caseInsensitive = attachmentNames.find((name) => name.toLowerCase() === folded);
  if (caseInsensitive) return caseInsensitive;

  const basename = sourceFile.split(/[\\/]/).pop()?.toLowerCase();
  if (basename) {
    const basenameMatch = attachmentNames.find((name) => name.toLowerCase() === basename);
    if (basenameMatch) return basenameMatch;
  }

  if (attachmentNames.length === 1 && (evidence?.source_page != null || evidence?.source_quote)) {
    return attachmentNames[0];
  }

  return null;
}

function mailContainsQuote(mail: MailMeta, quote: string | null | undefined): boolean {
  const cleaned = quote?.trim();
  if (!cleaned) return false;

  const body = (mail.body || "").toLocaleLowerCase("de-DE");
  if (!body) return false;
  return body.includes(cleaned.toLocaleLowerCase("de-DE"));
}
