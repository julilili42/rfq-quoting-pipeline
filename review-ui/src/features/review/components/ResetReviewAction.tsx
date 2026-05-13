import { useState } from "react";
import { RotateCcw } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { useResetReview } from "../hooks/useReviewMutations";

interface ResetReviewActionProps {
  reviewId: string;
}

export function ResetReviewAction({ reviewId }: ResetReviewActionProps) {
  const [armed, setArmed] = useState(false);
  const reset = useResetReview(reviewId);

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setArmed(true)}
        className="gap-1.5 text-muted-foreground"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Neustart
      </Button>

      {armed && (
        <div className="absolute right-0 top-full z-20 mt-1 w-64 space-y-2 rounded-md border border-danger/40 bg-danger-soft p-3 shadow-lg">
          <div className="text-[11.5px] font-semibold text-danger">
            Die Pipeline wird neu gestartet. Alle bisherigen Änderungen gehen verloren.
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="danger"
              size="sm"
              disabled={reset.isPending}
              onClick={() => {
                reset.mutate(undefined, {
                  onSettled: () => setArmed(false),
                });
              }}
            >
              {reset.isPending ? "Läuft…" : "Bestätigen"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setArmed(false)}>
              Abbrechen
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
