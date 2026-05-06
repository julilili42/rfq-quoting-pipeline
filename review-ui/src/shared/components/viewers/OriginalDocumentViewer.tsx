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
import { TabularPreview } from "./TabularPreview";
import type { MailMeta } from "@/shared/api/reviews";

interface OriginalDocumentViewerProps {
  reviewId: string;
  mail: MailMeta;
  attachmentNames?: string[];
  activeEvidence?: Evidence | null;
  className?: string;
}

const INLINE_RENDERABLE = new Set(["pdf", "png", "jpg", "jpeg"]);
const TABULAR = new Set(["csv", "tsv", "xlsx", "xls"]);

export function OriginalDocumentViewer({
  reviewId,
  mail,
  attachmentNames = [],
  activeEvidence,
  className,
}: OriginalDocumentViewerProps) {
  const defaultTab = attachmentNames.length > 0 ? attachmentNames[0] : "mail";
  const [activeTab, setActiveTab] = useState(defaultTab);

  // Switch tab when evidence points to a specific file.
  useEffect(() => {
    if (!activeEvidence) return;
    const file = activeEvidence.source_file;
    if (file === "mail" || !file) {
      setActiveTab("mail");
    } else if (attachmentNames.includes(file)) {
      setActiveTab(file);
    }
  }, [activeEvidence, attachmentNames]);

  return (
    <div className={cn("flex flex-col", className)}>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
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
            isActive && activeEvidence?.source_file === name
              ? activeEvidence
              : null;

          // Include page fragment when evidence points to a specific page.
          // Using a key that includes the page forces the iframe to reload
          // and jump to that page.
          const sourcePage = evidenceForThisFile?.source_page ?? null;
          const renderUrl = `${url}?v=${Date.now()}${sourcePage ? `#page=${sourcePage}` : ""}`;
          const iframeKey = `${name}-p${sourcePage ?? 0}`;

          return (
            <TabsContent key={name} value={name}>
              <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card">
                <header className="flex items-center justify-between gap-2 border-b border-border bg-muted px-4 py-2">
                  <span className="truncate text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Original · {name}
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

                {INLINE_RENDERABLE.has(suffix) ? (
                  <iframe
                    key={iframeKey}
                    src={renderUrl}
                    title={`Original · ${name}`}
                    className="block min-h-[700px] w-full flex-1 border-0 bg-surface"
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

        <TabsContent value="mail">
          <MailBodyViewer
            mail={mail}
            highlightQuote={
              activeEvidence?.source_file === "mail" ||
              !activeEvidence?.source_file
                ? (activeEvidence?.source_quote ?? null)
                : null
            }
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
