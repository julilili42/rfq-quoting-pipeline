import { useQuery } from "@tanstack/react-query";
import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { RotateCcw } from "lucide-react";
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
  const renderedPagesRef = useRef<Set<number>>(new Set());
  const [pageWidth, setPageWidth] = useState(760);
  const [numPages, setNumPages] = useState(0);
  const [renderTick, setRenderTick] = useState(0);
  const [zoom, setZoom] = useState(1.0);

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

  const markPageRendered = useCallback((pageIndex: number) => {
    if (renderedPagesRef.current.has(pageIndex)) return;
    renderedPagesRef.current.add(pageIndex);
    setRenderTick((value) => value + 1);
  }, []);

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
    const viewport = viewportRef.current;
    if (!viewport) return;

    const handleWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      setZoom((prev) => Math.min(3.0, Math.max(0.25, prev * (1 - e.deltaY * 0.001))));
    };

    viewport.addEventListener("wheel", handleWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleWheel);
  }, []);

  useEffect(() => {
    if (!numPages || !sourceTarget || highlightQuery.isLoading) return;

    const targetPage = Math.max(0, Math.min(numPages - 1, initialPage));
    const area = highlightAreas.find((item) => item.pageIndex === targetPage) ?? null;

    let cancelled = false;
    let timeout: number | undefined;
    let attempts = 0;

    const scrollToTarget = () => {
      if (cancelled) return;
      attempts += 1;

      const pageElement = pageRefs.current[targetPage];
      const viewport = viewportRef.current;
      if (
        !pageElement ||
        !viewport ||
        pageElement.clientHeight <= 0 ||
        !renderedPagesRef.current.has(targetPage)
      ) {
        if (attempts < 20) {
          timeout = window.setTimeout(scrollToTarget, 50);
        }
        return;
      }

      const pageRect = pageElement.getBoundingClientRect();
      const viewportRect = viewport.getBoundingClientRect();
      const top =
        pageRect.top -
        viewportRect.top +
        viewport.scrollTop;
      const highlightTop = area ? (area.top / 100) * pageElement.clientHeight : 0;
      const highlightHeight = area ? (area.height / 100) * pageElement.clientHeight : 0;
      const viewportOffset = area
        ? Math.max(80, (viewport.clientHeight - highlightHeight) * 0.35)
        : 16;

      viewport.scrollTo({
        top: Math.max(0, top + highlightTop - viewportOffset),
        behavior: "smooth",
      });
    };

    timeout = window.setTimeout(scrollToTarget, 0);

    return () => {
      cancelled = true;
      if (timeout !== undefined) window.clearTimeout(timeout);
    };
  }, [
    highlightAreas,
    highlightQuery.data?.pageIndex,
    highlightQuery.isLoading,
    initialPage,
    numPages,
    pageWidth,
    renderTick,
    sourceTarget,
    targetKey,
  ]);

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

      <div className="flex min-h-0 flex-1 flex-col">
        {zoom !== 1.0 && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-b border-border bg-muted px-3 py-1 text-xs text-muted-foreground">
            <span className="tabular-nums">{Math.round(zoom * 100)}%</span>
            <button
              type="button"
              onClick={() => setZoom(1.0)}
              title="Zoom zurücksetzen"
              className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-border hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" />
              Zurücksetzen
            </button>
          </div>
        )}
        <div
          ref={viewportRef}
          className="scrollbar-none min-h-0 flex-1 overflow-auto bg-muted/40 px-4 py-4"
        >
          {/* CSS zoom scales visually without changing the canvas width → no re-render */}
          <div style={{ zoom }}>
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
                  renderedPagesRef.current = new Set();
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
                    onRenderSuccess={() => markPageRendered(index)}
                  />
                ))}
              </Document>
            </PdfRenderBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}

function PdfPage({
  pageNumber,
  width,
  highlights,
  onRenderSuccess,
  refCallback,
}: {
  pageNumber: number;
  width: number;
  highlights: PdfHighlightArea[];
  onRenderSuccess?: () => void;
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
        onRenderSuccess={onRenderSuccess}
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
