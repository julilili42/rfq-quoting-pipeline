import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

interface DatePopoverProps {
  value: string;
  onChange: (next: string) => void;
  children: (state: { toggle: () => void; isOpen: boolean }) => ReactNode;
}

const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const MONTHS = [
  "Januar",
  "Februar",
  "März",
  "April",
  "Mai",
  "Juni",
  "Juli",
  "August",
  "September",
  "Oktober",
  "November",
  "Dezember",
];

export function DatePopover({ value, onChange, children }: DatePopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState<Date>(() =>
    startOfMonth(parseGerman(value) ?? new Date()),
  );
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setViewMonth(startOfMonth(parseGerman(value) ?? new Date()));
  }, [isOpen, value]);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [isOpen]);

  const cells = useMemo(() => buildGrid(viewMonth), [viewMonth]);
  const selected = parseGerman(value);
  const today = new Date();

  const pickDate = (date: Date) => {
    onChange(formatGerman(date));
    setIsOpen(false);
  };

  return (
    <div ref={wrapperRef} className="relative">
      {children({ toggle: () => setIsOpen((open) => !open), isOpen })}
      {isOpen && (
        <div
          role="dialog"
          aria-label="Datum wählen"
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-lg border border-border bg-surface p-3 shadow-card-hover"
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() =>
                setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))
              }
              aria-label="Voriger Monat"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="font-display text-sm font-semibold tracking-tight text-foreground">
              {MONTHS[viewMonth.getMonth()]} {viewMonth.getFullYear()}
            </span>
            <button
              type="button"
              onClick={() =>
                setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))
              }
              aria-label="Nächster Monat"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mb-1 grid grid-cols-7 text-center text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {WEEKDAYS.map((day) => (
              <span key={day} className="py-1">
                {day}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-y-0.5 text-sm">
            {cells.map((date) => {
              const inMonth = date.getMonth() === viewMonth.getMonth();
              const isToday = isSameDay(date, today);
              const isSelected = selected ? isSameDay(date, selected) : false;
              return (
                <button
                  key={date.toISOString()}
                  type="button"
                  onClick={() => pickDate(date)}
                  className={cn(
                    "mx-auto h-8 w-8 rounded-md text-center font-medium transition-colors",
                    isSelected
                      ? "bg-brand text-white shadow-sm hover:bg-brand-dark"
                      : inMonth
                        ? "text-foreground hover:bg-brand-soft hover:text-brand"
                        : "text-muted-foreground/40 hover:bg-muted",
                    !isSelected && isToday && "ring-1 ring-brand/50",
                  )}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>

          <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-xs">
            <button
              type="button"
              onClick={() => pickDate(new Date())}
              className="font-semibold text-brand transition-colors hover:text-brand-dark"
            >
              Heute
            </button>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Schließen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function parseGerman(value: string): Date | null {
  const match = value.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!match) return null;
  const [, d, mo, y] = match;
  const date = new Date(Number(y), Number(mo) - 1, Number(d));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatGerman(date: Date): string {
  const d = String(date.getDate()).padStart(2, "0");
  const m = String(date.getMonth() + 1).padStart(2, "0");
  return `${d}.${m}.${date.getFullYear()}`;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function buildGrid(viewMonth: Date): Date[] {
  const first = startOfMonth(viewMonth);
  const weekday = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - weekday);

  const cells: Date[] = [];
  for (let i = 0; i < 42; i++) {
    const cell = new Date(start);
    cell.setDate(start.getDate() + i);
    cells.push(cell);
  }
  return cells;
}
