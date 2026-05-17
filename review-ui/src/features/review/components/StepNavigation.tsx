import { ArrowLeft, ArrowRight } from "lucide-react";
import { useCallback } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/shared/components/ui/button";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";

const STEP_ORDER = ["positions", "approval"] as const;
type Slug = (typeof STEP_ORDER)[number];

interface StepNavigationProps {
  current: Slug;
  forwardLabel?: string;
  backLabel?: string;
  /**
   * Final-step "finish" callback. When provided on the last step,
   * replaces the next button with a finish button.
   */
  onFinish?: () => void;
  finishLabel?: string;
  disabled?: boolean;
}

export function StepNavigation({
  current,
  forwardLabel = "Weiter",
  backLabel = "Zurück",
  onFinish,
  finishLabel = "Fertig",
  disabled = false,
}: StepNavigationProps) {
  const { reviewId } = useParams<{ reviewId: string }>();
  const navigate = useNavigate();
  const idx = STEP_ORDER.indexOf(current);
  const prev = idx > 0 ? STEP_ORDER[idx - 1] : null;
  const next = idx < STEP_ORDER.length - 1 ? STEP_ORDER[idx + 1] : null;

  const goNext = useCallback(() => {
    if (disabled) return;
    if (next) navigate(`/reviews/${encodeURIComponent(reviewId ?? "")}/${next}`);
    else onFinish?.();
  }, [disabled, next, navigate, reviewId, onFinish]);

  const goPrev = useCallback(() => {
    if (prev) navigate(`/reviews/${encodeURIComponent(reviewId ?? "")}/${prev}`);
  }, [prev, navigate, reviewId]);

  useHotkeys("alt+arrowright", goNext, { enabled: !!reviewId, preventDefault: true });
  useHotkeys("alt+arrowleft", goPrev, { enabled: !!reviewId, preventDefault: true });

  return (
    <>
      <div aria-hidden="true" className="mt-8 h-24" />
      <nav
        aria-label="Schritt-Navigation"
        className="fixed bottom-0 left-0 right-0 z-30 border-t border-border bg-background/95 shadow-[0_-8px_24px_hsl(var(--foreground)/0.06)] backdrop-blur-sm lg:left-64"
      >
        <div className="mx-auto flex h-20 w-full max-w-screen-2xl items-center justify-between gap-4 px-6">
          <div>
            {prev && (
              <div className="group relative">
                <Button variant="secondary" onClick={goPrev}>
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  {backLabel}
                </Button>
                <ShortcutHint keys={["Alt", "←"]} placement="top" />
              </div>
            )}
          </div>

          <div>
            {next ? (
              <div className="group relative">
                <Button variant="primary" disabled={disabled} onClick={goNext}>
                  {forwardLabel}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
                <ShortcutHint keys={["Alt", "→"]} placement="top" />
              </div>
            ) : onFinish ? (
              <div className="group relative">
                <Button variant="primary" onClick={onFinish}>
                  {finishLabel}
                </Button>
                <ShortcutHint keys={["Alt", "→"]} placement="top" />
              </div>
            ) : null}
          </div>
        </div>
      </nav>
    </>
  );
}
