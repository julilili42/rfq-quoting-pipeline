import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

interface ResizableSplitProps {
  left: ReactNode;
  right: ReactNode;
  /** Initial width of the left pane, in percent of the container. */
  defaultLeftPct?: number;
  /** Smallest width either pane may shrink to, in percent. */
  minPct?: number;
  className?: string;
}

/**
 * Two panes side by side with a draggable divider, for the fullscreen
 * document comparison. The split is stored as a single percentage so it
 * survives container/viewport resizes — the right pane just takes the
 * remainder. Dragging works for mouse, touch and pen (pointer events); the
 * divider is keyboard-operable (←/→, Home to reset) for accessibility.
 */
export function ResizableSplit({
  left,
  right,
  defaultLeftPct = 50,
  minPct = 25,
  className,
}: ResizableSplitProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [leftPct, setLeftPct] = useState(defaultLeftPct);
  const [dragging, setDragging] = useState(false);

  const clamp = useCallback(
    (pct: number) => Math.min(100 - minPct, Math.max(minPct, pct)),
    [minPct],
  );

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0) return;
      setLeftPct(clamp(((event.clientX - rect.left) / rect.width) * 100));
    };
    const onUp = () => setDragging(false);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    // Keep the cursor and selection stable while dragging over the iframes.
    const prevUserSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;
    };
  }, [dragging, clamp]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setLeftPct((pct) => clamp(pct - 2));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setLeftPct((pct) => clamp(pct + 2));
    } else if (event.key === "Home") {
      event.preventDefault();
      setLeftPct(50);
    }
  };

  return (
    <div ref={containerRef} className={cn("flex min-h-0 w-full", className)}>
      <div
        className="min-h-0 min-w-0 shrink-0"
        style={{ width: `${leftPct}%` }}
      >
        {left}
      </div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={Math.round(leftPct)}
        aria-valuemin={minPct}
        aria-valuemax={100 - minPct}
        aria-label="Bereiche anpassen — Ziehen, ←/→ oder Home zum Zurücksetzen"
        tabIndex={0}
        onPointerDown={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDoubleClick={() => setLeftPct(50)}
        onKeyDown={onKeyDown}
        className={cn(
          "group relative mx-1.5 flex w-1 shrink-0 cursor-col-resize items-center justify-center rounded-full transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          dragging ? "bg-brand" : "bg-border hover:bg-brand/50",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none h-10 w-1 rounded-full transition-colors",
            dragging
              ? "bg-brand"
              : "bg-muted-foreground/30 group-hover:bg-brand/60",
          )}
        />
      </div>

      <div className="min-h-0 min-w-0 flex-1">{right}</div>
    </div>
  );
}
