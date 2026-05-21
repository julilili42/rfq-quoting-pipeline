import { useQuery } from "@tanstack/react-query";
import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { reviewsApi, type PdfHighlightArea } from "@/shared/api/reviews";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { cn } from "@/shared/lib/cn";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

interface PdfSourcePreviewProps {
  reviewId: string;
  fileName: string;
  fileUrl: string;
  sourceTarget?: SourceNavigationTarget | null;
  className?: string;
}

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MAX_PAGE_WIDTH = 980;
const VIEWPORT_PADDING = 32;

class PdfRenderBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[PdfSourcePreview]", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorState
          title="PDF konnte nicht gerendert werden"
          error={this.state.error}
          className="m-3"
        />
      );
    }

    return this.props.children;
  }
}

export function PdfSourcePreview({
  reviewId,
  fileName,
  fileUrl,
  sourceTarget,
  className,
}: PdfSourcePreviewProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [pageWidth, setPageWidth] = useState(760);
  const [numPages, setNumPages] = useState(0);

  const targetKey = useMemo(
    () => (sourceTarget ? JSON.stringify(sourceTarget) : "none"),
    [sourceTarget],
  );

  const highlightQuery = useQuery({
    queryKey: ["pdf-source-highlight", reviewId, fileName, targetKey],
    queryFn: () => reviewsApi.pdfHighlight(reviewId, fileName, sourceTarget!),
    enabled: Boolean(sourceTarget),
    staleTime: 5 * 60_000,
  });

  const highlightAreas = useMemo(
    () => highlightQuery.data?.areas ?? [],
    [highlightQuery.data?.areas],
  );

  const initialPage =
    highlightAreas[0]?.pageIndex ??
    highlightQuery.data?.pageIndex ??
    ((sourceTarget?.evidence.source_page ?? 1) - 1);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const measure = () => {
      const nextWidth = Math.min(
        MAX_PAGE_WIDTH,
        Math.max(320, viewport.clientWidth - VIEWPORT_PADDING),
      );
      setPageWidth(Math.floor(nextWidth));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!numPages || !sourceTarget) return;

    const targetPage = Math.max(0, Math.min(numPages - 1, initialPage));
    const pageElement = pageRefs.current[targetPage];
    const viewport = viewportRef.current;
    if (!pageElement || !viewport) return;

    const timeout = window.setTimeout(() => {
      const top =
        pageElement.getBoundingClientRect().top -
        viewport.getBoundingClientRect().top +
        viewport.scrollTop;
      viewport.scrollTo({ top, behavior: "smooth" });
    }, 180);

    return () => window.clearTimeout(timeout);
  }, [initialPage, numPages, sourceTarget, targetKey]);

  return (
    <div className={cn("flex flex-col", className ?? "h-[700px]")}>
      {highlightQuery.isLoading && (
        <LoadingState label="Quelle wird gesucht…" className="border-b border-border py-3" />
      )}
      {highlightQuery.isError && (
        <ErrorState error={highlightQuery.error} className="border-b border-border" />
      )}
      {highlightQuery.data?.status === "page_only" && (
        <p className="border-b border-border bg-warning-soft px-4 py-2 text-xs text-warning">
          Seite gefunden, aber keine markierbare Textstelle. Das passiert bei
          gescannten oder bildbasierten PDFs ohne Textlayer.
        </p>
      )}
      {highlightQuery.data?.status === "not_found" && (
        <p className="border-b border-border bg-muted px-4 py-2 text-xs text-muted-foreground">
          Keine passende Textstelle im PDF gefunden.
        </p>
      )}

      <div
        ref={viewportRef}
        className="min-h-0 flex-1 overflow-auto bg-muted/40 px-4 py-4"
      >
        <PdfRenderBoundary key={fileUrl}>
          <Document
            file={fileUrl}
            loading={<LoadingState label="PDF wird geladen…" />}
            error={
              <ErrorState
                title="PDF konnte nicht geladen werden"
                error="Die Datei ist nicht verfügbar oder kann vom Browser nicht gelesen werden."
                className="m-3"
              />
            }
            onLoadSuccess={({ numPages: nextNumPages }) => {
              setNumPages(nextNumPages);
              pageRefs.current = Array(nextNumPages).fill(null);
            }}
            onLoadError={(error) => {
              console.error("[PdfSourcePreview] PDF load failed", error);
            }}
          >
            {Array.from({ length: numPages }, (_, index) => (
              <PdfPage
                key={`${fileUrl}-${index}`}
                refCallback={(element) => {
                  pageRefs.current[index] = element;
                }}
                pageNumber={index + 1}
                width={pageWidth}
                highlights={highlightAreas.filter((area) => area.pageIndex === index)}
              />
            ))}
          </Document>
        </PdfRenderBoundary>
      </div>
    </div>
  );
}

function PdfPage({
  pageNumber,
  width,
  highlights,
  refCallback,
}: {
  pageNumber: number;
  width: number;
  highlights: PdfHighlightArea[];
  refCallback: (element: HTMLDivElement | null) => void;
}) {
  return (
    <div
      ref={refCallback}
      className="relative mx-auto mb-4 w-fit overflow-hidden rounded-md bg-surface shadow-card"
    >
      <Page
        pageNumber={pageNumber}
        width={width}
        loading={<LoadingState label={`Seite ${pageNumber} wird geladen…`} />}
        renderAnnotationLayer
        renderTextLayer
      />
      {highlights.length > 0 && (
        <div className="pointer-events-none absolute inset-0">
          {highlights.map((area, index) => (
            <div
              key={`${area.pageIndex}-${area.left}-${area.top}-${index}`}
              data-testid="pdf-source-highlight"
              className="absolute rounded-[2px] bg-amber-300/40 ring-1 ring-amber-500/80"
              style={{
                left: `${area.left}%`,
                top: `${area.top}%`,
                width: `${area.width}%`,
                height: `${area.height}%`,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
