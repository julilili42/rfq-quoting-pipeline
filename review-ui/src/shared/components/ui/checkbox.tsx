import { Check, Minus } from "lucide-react";
import * as React from "react";

import { cn } from "@/shared/lib/cn";

interface CheckboxProps {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  onCheckedChange: () => void;
  ariaLabel: string;
  className?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    { checked, indeterminate = false, disabled = false, onCheckedChange, ariaLabel, className },
    ref,
  ) {
    return (
      <label
        className={cn(
          "inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-md transition-colors",
          "hover:bg-surface-sunk focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1",
          disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
          className,
        )}
      >
        <input
          ref={ref}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-label={ariaLabel}
          onChange={onCheckedChange}
          className="sr-only"
        />
        <span
          aria-hidden="true"
          className={cn(
            "flex h-[18px] w-[18px] items-center justify-center rounded-[5px] border transition-colors",
            checked || indeterminate
              ? "border-brand bg-brand text-white shadow-sm"
              : "border-border bg-surface group-hover:border-foreground/30",
          )}
        >
          {indeterminate ? (
            <Minus className="h-3 w-3" strokeWidth={3} />
          ) : checked ? (
            <Check className="h-3 w-3" strokeWidth={3} />
          ) : null}
        </span>
      </label>
    );
  },
);
