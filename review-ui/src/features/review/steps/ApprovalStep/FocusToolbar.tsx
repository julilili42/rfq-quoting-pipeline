import { Minimize2 } from "lucide-react";
import { useCallback } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { Pill } from "@/shared/components/ui/pill";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";

interface FocusToolbarProps {
  reviewId: string;
  fileName?: string;
}

/**
 * Slim toolbar shown at the top of the fullscreen comparison view.
 * Shows the review id and a button to drop back into the normal layout.
 */
export function FocusToolbar({ reviewId, fileName }: FocusToolbarProps) {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const exitFocus = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("focus");
    navigate({ search: next.toString() });
  }, [navigate, params]);

  useHotkeys("esc", exitFocus, {
    enableOnFormTags: true,
    preventDefault: true,
  });

  return (
    <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-2 shadow-card">
      <div className="flex min-w-0 items-center gap-3">
        <span className="font-display text-sm font-bold tracking-tight">
          Vollbild
        </span>
        <Pill tone="neutral">
          <code className="font-mono text-[10.5px]">{reviewId}</code>
        </Pill>
        {fileName && (
          <span className="truncate text-xs text-muted-foreground">
            {fileName}
          </span>
        )}
      </div>

      <div className="group relative">
        <Button variant="secondary" size="sm" onClick={exitFocus}>
          <Minimize2 className="h-4 w-4" aria-hidden="true" />
          Vollbild verlassen
        </Button>
        <ShortcutHint keys={["Esc"]} />
      </div>
    </div>
  );
}
