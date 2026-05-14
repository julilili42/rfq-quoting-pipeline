import { Redo2, Undo2 } from "lucide-react";
import { useCallback } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { useReviewUiStore } from "../stores/reviewUiStore";
import { cn } from "@/shared/lib/cn";
import { useSaveAndRegenerate } from "../hooks/useReviewMutations";

/**
 * Inline badge showing how many fields the user has touched since
 * the LLM extraction. Mirrors the Streamlit `_changes_indicator`.
 */
export function ChangedFieldsIndicator({ className }: { className?: string }) {
  const reviewId = useReviewUiStore((s) => s.activeReviewId);
  const count = useReviewUiStore((s) => s.changedFields.size);
  const canUndo = useReviewUiStore((s) => s.undoStack.length > 0);
  const canRedo = useReviewUiStore((s) => s.redoStack.length > 0);
  const undoSnapshot = useReviewUiStore((s) => s.undoSnapshot);
  const redoSnapshot = useReviewUiStore((s) => s.redoSnapshot);
  const saveAndRegenerate = useSaveAndRegenerate(reviewId ?? undefined);

  const restoreSnapshot = useCallback(
    (direction: "undo" | "redo") => {
      if (saveAndRegenerate.isPending) return;
      const snapshot = direction === "undo" ? undoSnapshot() : redoSnapshot();
      if (!snapshot) return;
      saveAndRegenerate.mutate({
        anfrage: snapshot.anfrage,
        overrides: snapshot.manualOverrides,
      });
    },
    [redoSnapshot, saveAndRegenerate, undoSnapshot],
  );

  const undo = useCallback(() => restoreSnapshot("undo"), [restoreSnapshot]);
  const redo = useCallback(() => restoreSnapshot("redo"), [restoreSnapshot]);

  useHotkeys("alt+z", undo, {
    enabled: canUndo && !saveAndRegenerate.isPending,
    enableOnFormTags: true,
    preventDefault: true,
  });
  useHotkeys("shift+alt+z", redo, {
    enabled: canRedo && !saveAndRegenerate.isPending,
    enableOnFormTags: true,
    preventDefault: true,
  });

  if (count === 0 && !canRedo) return null;

  return (
    <div
      title="Änderungen gegenüber KI-Extraktion"
      className={cn(
        "inline-flex items-center gap-1 rounded border border-border bg-surface px-1.5 py-0.5 text-xs font-medium text-muted-foreground",
        className,
      )}
    >
      <strong>{count}</strong>{" "}
      <span>{count === 1 ? "Änderung" : "Änderungen"}</span>
      <span className="mx-0.5 h-3.5 w-px bg-border" aria-hidden="true" />
      <button
        type="button"
        aria-label="Letzte Änderung zurücknehmen"
        title="Zurücknehmen (Alt+Z)"
        disabled={!canUndo || saveAndRegenerate.isPending}
        onClick={() => restoreSnapshot("undo")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-35"
      >
        <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label="Zurückgenommene Änderung wiederherstellen"
        title="Wiederherstellen (Shift+Alt+Z)"
        disabled={!canRedo || saveAndRegenerate.isPending}
        onClick={() => restoreSnapshot("redo")}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-35"
      >
        <Redo2 className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
