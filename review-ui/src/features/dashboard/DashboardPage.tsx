import { Inbox } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/shared/components/feedback/EmptyState";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { UploadDropzone } from "@/features/upload/UploadDropzone";

import { DashboardHero } from "./components/DashboardHero";
import {
  ReviewFilters,
  type DatePreset,
  type SortOption,
  type StatusFilter,
} from "./components/ReviewFilters";
import { ReviewList } from "./components/ReviewList";
import { useReviewSummaries } from "./hooks/useReviewSummaries";

function isWithinPreset(dateStr: string, preset: DatePreset): boolean {
  if (preset === "all") return true;
  const date = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (preset === "today") return date >= today;
  const cutoff = new Date(today);
  cutoff.setDate(today.getDate() - (preset === "week" ? 7 : 30));
  return date >= cutoff;
}

export function DashboardPage() {
  const { data: reviews, isLoading, isError, error } = useReviewSummaries();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [sortBy, setSortBy] = useState<SortOption>("date_desc");

  const filtered = useMemo(() => {
    if (!reviews) return [];
    const q = query.trim().toLowerCase();
    const result = reviews.filter((r) => {
      if (status !== "all" && r.status !== status) return false;
      if (!isWithinPreset(r.created_at, datePreset)) return false;
      if (!q) return true;
      return r.subject.toLowerCase().includes(q) || r.sender.toLowerCase().includes(q);
    });

    return [...result].sort((a, b) => {
      switch (sortBy) {
        case "date_desc":
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        case "date_asc":
          return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
        case "amount_desc":
          return b.total_eur - a.total_eur;
        case "amount_asc":
          return a.total_eur - b.total_eur;
      }
    });
  }, [reviews, status, query, datePreset, sortBy]);

  return (
    <PageContainer>
      <DashboardHero />

      <section className="mb-8">
        <UploadDropzone />
      </section>

      {isLoading && <LoadingState label="Lade Anfragen…" />}
      {isError && <ErrorState error={error} />}

      {!isLoading && !isError && reviews && reviews.length === 0 && (
        <EmptyState
          icon={Inbox}
          title="Noch keine Anfragen vorhanden"
          description="Sobald aus Outlook eine Anfrage an die Review-API gesendet wird, erscheint sie hier. Alternativ einfach eine Datei oben ablegen."
        />
      )}

      {!isLoading && !isError && reviews && reviews.length > 0 && (
        <section>
          <ReviewFilters
            status={status}
            query={query}
            datePreset={datePreset}
            sortBy={sortBy}
            onStatusChange={setStatus}
            onQueryChange={setQuery}
            onDatePresetChange={setDatePreset}
            onSortByChange={setSortBy}
            totalCount={reviews.length}
            filteredCount={filtered.length}
          />
          <ReviewList
            reviews={filtered}
          />
        </section>
      )}
    </PageContainer>
  );
}
