import type { Evidence } from "@/shared/schemas/anfrage";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";
import { cn } from "@/shared/lib/cn";

import { Label } from "./label";
import { SourceEyeButton } from "./SourceEyeButton";

interface FormFieldProps {
  label: string;
  /** Shown inline in muted text after the label. */
  hint?: string;
  /** When set, renders source controls next to the label. */
  evidence?: Evidence;
  sourceTarget?: SourceNavigationTarget;
  onNavigate?: (target: SourceNavigationTarget) => void;
  sourceButtonClassName?: string;
  children: React.ReactNode;
}

export function FormField({
  label,
  hint,
  evidence,
  sourceTarget,
  onNavigate,
  sourceButtonClassName,
  children,
}: FormFieldProps) {
  const hasSourceButton = Boolean(sourceTarget && onNavigate);

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">
        {label}
        {hint && (
          <span className="ml-1 font-normal text-muted-foreground">· {hint}</span>
        )}
      </Label>

      <div
        className={cn(
          "relative min-w-0",
          hasSourceButton && "[&_input]:pr-11 [&_textarea]:pr-11",
        )}
      >
        {children}

        {hasSourceButton && sourceTarget && onNavigate && (
          <div className={cn("absolute right-1 top-1 z-10", sourceButtonClassName)}>
            <SourceEyeButton
              sourceTarget={sourceTarget}
              onNavigate={onNavigate}
              evidence={evidence}
              className="h-8 w-8"
            />
          </div>
        )}
      </div>
    </div>
  );
}
