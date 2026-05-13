import { Worker, Viewer, ScrollMode, SpecialZoomLevel } from "@react-pdf-viewer/core";
import {
  highlightPlugin,
  Trigger,
  type HighlightArea,
  type RenderHighlightsProps,
} from "@react-pdf-viewer/highlight";
import { useQuery } from "@tanstack/react-query";
import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  type ErrorInfo,
  type ReactNode,
} from "react";

import { reviewsApi } from "@/shared/api/reviews";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { cn } from "@/shared/lib/cn";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/highlight/lib/styles/index.css";

interface PdfSourcePreviewProps {
  reviewId: string;
  fileName: string;
  fileUrl: string;
  sourceTarget?: SourceNavigationTarget | null;
  className?: string;
}

const workerUrl = new URL("pdfjs-dist/build/pdf.worker.min.js", import.meta.url).toString();
const JUMP_TOP_MARGIN_PERCENT = 9;

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

  const highlightAreas = useMemo<HighlightArea[]>(
    () => highlightQuery.data?.areas ?? [],
    [highlightQuery.data?.areas],
  );

  const initialPage =
    highlightAreas[0]?.pageIndex ??
    highlightQuery.data?.pageIndex ??
    ((sourceTarget?.evidence.source_page ?? 1) - 1);

  const renderHighlights = useCallback(
    (props: RenderHighlightsProps) => (
      <>
        {highlightAreas
          .filter((area) => area.pageIndex === props.pageIndex)
          .map((area, index) => (
            <div
              key={`${area.pageIndex}-${area.left}-${area.top}-${index}`}
              data-testid="pdf-source-highlight"
              className="rounded-[2px] bg-amber-300/40 ring-1 ring-amber-500/80"
              style={props.getCssProperties(area, props.rotation)}
            />
          ))}
      </>
    ),
    [highlightAreas],
  );

  const highlightPluginInstance = highlightPlugin({
    trigger: Trigger.None,
    renderHighlights,
  });
  const jumpTargetArea = useMemo<HighlightArea | null>(() => {
    const firstHighlightArea = highlightAreas[0];
    if (firstHighlightArea) return withJumpMargin(firstHighlightArea);

    if (highlightQuery.data?.pageIndex == null) return null;
    return {
      pageIndex: highlightQuery.data.pageIndex,
      left: 0,
      top: 0,
      width: 1,
      height: 1,
    };
  }, [highlightAreas, highlightQuery.data?.pageIndex]);

  useEffect(() => {
    if (!jumpTargetArea) return;

    const timeout = window.setTimeout(() => {
      highlightPluginInstance.jumpToHighlightArea(jumpTargetArea);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [highlightPluginInstance, jumpTargetArea]);

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

      <div className="min-h-0 flex-1 overflow-hidden bg-surface">
        <PdfRenderBoundary key={fileUrl}>
          <Worker workerUrl={workerUrl}>
            <Viewer
              key={fileUrl}
              fileUrl={fileUrl}
              defaultScale={SpecialZoomLevel.PageWidth}
              initialPage={Math.max(0, initialPage)}
              plugins={[highlightPluginInstance]}
              renderError={(error) => (
                <ErrorState
                  title="PDF konnte nicht geladen werden"
                  error={error}
                  className="m-3"
                />
              )}
              scrollMode={ScrollMode.Vertical}
            />
          </Worker>
        </PdfRenderBoundary>
      </div>
    </div>
  );
}

function withJumpMargin(area: HighlightArea): HighlightArea {
  const top = Math.max(0, area.top - JUMP_TOP_MARGIN_PERCENT);
  return {
    ...area,
    top,
    height: Math.min(100 - top, area.height + (area.top - top)),
  };
}
