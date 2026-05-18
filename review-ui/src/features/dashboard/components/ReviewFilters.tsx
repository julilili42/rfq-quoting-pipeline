import { CalendarDays, Search, SlidersHorizontal } from "lucide-react";

import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/cn";

import type { ReviewStatus } from "../schemas/reviewSummary";

export type StatusFilter = "all" | ReviewStatus;
export type DatePreset = "all" | "today" | "week" | "month";
export type SortOption = "date_desc" | "date_asc" | "amount_desc" | "amount_asc";

interface ReviewFiltersProps {
  status: StatusFilter;
  query: string;
  datePreset: DatePreset;
  sortBy: SortOption;
  onStatusChange: (s: StatusFilter) => void;
  onQueryChange: (q: string) => void;
  onDatePresetChange: (d: DatePreset) => void;
  onSortByChange: (s: SortOption) => void;
  totalCount: number;
  filteredCount: number;
}

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "Alle" },
  { value: "in_arbeit", label: "In Arbeit" },
  { value: "pdf_bereit", label: "Zu prüfen" },
  { value: "abgeschlossen", label: "Abgeschlossen" },
];

const DATE_OPTIONS: Array<{ value: DatePreset; label: string }> = [
  { value: "all", label: "Alle" },
  { value: "today", label: "Heute" },
  { value: "week", label: "7 Tage" },
  { value: "month", label: "30 Tage" },
];

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: "date_desc", label: "Neueste zuerst" },
  { value: "date_asc", label: "Älteste zuerst" },
  { value: "amount_desc", label: "Höchster Betrag" },
  { value: "amount_asc", label: "Niedrigster Betrag" },
];

function FilterPills<T extends string>({
  options,
  active,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string }>;
  active: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="radiogroup" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={active === opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-all",
            active === opt.value
              ? "bg-foreground text-white shadow-sm"
              : "border border-border bg-surface text-muted-foreground hover:border-foreground/30 hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function ReviewFilters({
  status,
  query,
  datePreset,
  sortBy,
  onStatusChange,
  onQueryChange,
  onDatePresetChange,
  onSortByChange,
  totalCount,
  filteredCount,
}: ReviewFiltersProps) {
  return (
    <div className="mb-4 space-y-3">
      {/* Row 1: search + sort */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative sm:w-80">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Kunde oder Betreff…"
            className="pl-9"
            aria-label="Anfragen durchsuchen"
          />
        </div>

        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <select
            value={sortBy}
            onChange={(e) => onSortByChange(e.target.value as SortOption)}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Sortierung"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Row 2: status + date pills + result count */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <FilterPills
            options={STATUS_OPTIONS}
            active={status}
            onChange={onStatusChange}
            label="Status-Filter"
          />
          <div className="h-4 w-px bg-border" aria-hidden="true" />
          <div className="flex items-center gap-1.5">
            <CalendarDays className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <FilterPills
              options={DATE_OPTIONS}
              active={datePreset}
              onChange={onDatePresetChange}
              label="Zeitraum-Filter"
            />
          </div>
        </div>

        <p className="shrink-0 text-xs text-muted-foreground">
          {filteredCount === totalCount
            ? `${totalCount} Anfrage${totalCount !== 1 ? "n" : ""}`
            : `${filteredCount} von ${totalCount} Anfragen`}
        </p>
      </div>
    </div>
  );
}
