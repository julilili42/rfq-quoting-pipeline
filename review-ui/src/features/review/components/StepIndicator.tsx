import { Check } from "lucide-react";
import { NavLink, useLocation, useParams } from "react-router-dom";

import { cn } from "@/shared/lib/cn";

const STEPS = [
  {
    num: 1,
    slug: "positions",
    title: "Anfrage vorbereiten",
  },
  {
    num: 2,
    slug: "approval",
    title: "Vergleichen & freigeben",
  },
] as const;

type StepSlug = (typeof STEPS)[number]["slug"];

function activeStepFromPath(pathname: string): StepSlug {
  if (pathname.endsWith("/approval")) return "approval";
  return "positions";
}

export function StepIndicator() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const location = useLocation();
  const active = activeStepFromPath(location.pathname);
  const activeIndex = STEPS.findIndex((s) => s.slug === active);

  return (
    <ol className="grid grid-cols-1 gap-3 md:grid-cols-2" aria-label="Workflow-Schritte">
      {STEPS.map((step, index) => {
        const isDone = index < activeIndex;
        const isActive = index === activeIndex;
        const isClickable = isDone || isActive;
        const target = `/reviews/${encodeURIComponent(reviewId ?? "")}/${step.slug}`;

        const inner = (
          <>
            <span
              className={cn(
                "absolute inset-x-0 top-0 h-1",
                isActive
                  ? "bg-brand"
                  : isDone
                    ? "bg-success"
                    : "bg-border",
              )}
              aria-hidden="true"
            />
            <div
              className={cn(
                "mb-1 flex items-center gap-2 font-display text-xs font-bold uppercase tracking-wider",
                isActive
                  ? "text-brand"
                  : isDone
                    ? "text-success"
                    : "text-muted-foreground/60",
              )}
            >
              {isDone ? (
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <span>{`0${step.num}`}</span>
              )}
            </div>
            <div className="font-display text-base font-bold tracking-tight">
              {step.title}
            </div>
          </>
        );

        const baseCls = cn(
          "relative block overflow-hidden rounded-lg border border-border bg-surface px-5 pt-4 pb-4 shadow-card transition-all",
          isClickable && "cursor-pointer hover:border-foreground/30 hover:shadow-card-hover",
        );

        return (
          <li key={step.slug}>
            {isClickable ? (
              <NavLink to={target} className={baseCls}>
                {inner}
              </NavLink>
            ) : (
              <div className={cn(baseCls, "cursor-default opacity-60")}>{inner}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
