import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Inbox, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { reviewsApi } from "@/shared/api/reviews";
import { reviewListQueryKey } from "@/shared/api/queryKeys";
import { EmptyState } from "@/shared/components/feedback/EmptyState";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
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
  const queryClient = useQueryClient();
  const { data: reviews, isLoading, isError, error } = useReviewSummaries();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [sortBy, setSortBy] = useState<SortOption>("date_desc");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

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

  useEffect(() => {
    if (!reviews) return;
    const knownIds = new Set(reviews.map((review) => review.review_id));
    setSelectedIds((prev) => {
      const next = new Set([...prev].filter((id) => knownIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [reviews]);

  const selectedReviewIds = useMemo(
    () => Array.from(selectedIds),
    [selectedIds],
  );

  const deleteMutation = useMutation({
    mutationFn: (reviewIds: string[]) => reviewsApi.deleteMany(reviewIds),
    onSuccess: (_result, reviewIds) => {
      setDeleteDialogOpen(false);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        reviewIds.forEach((id) => next.delete(id));
        return next;
      });
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });

  const toggleReviewSelection = (reviewId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(reviewId)) {
        next.delete(reviewId);
      } else {
        next.add(reviewId);
      }
      return next;
    });
  };

  const setReviewsSelected = (reviewIds: string[], selected: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      reviewIds.forEach((id) => {
        if (selected) {
          next.add(id);
        } else {
          next.delete(id);
        }
      });
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const confirmDeleteSelected = () => {
    if (selectedReviewIds.length === 0) return;
    deleteMutation.mutate(selectedReviewIds);
  };

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
        <section className="pb-24">
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
            selectedIds={selectedIds}
            selectionDisabled={deleteMutation.isPending}
            onToggleReview={toggleReviewSelection}
            onSetReviewsSelected={setReviewsSelected}
          />
          <DeleteReviewsDialog
            open={deleteDialogOpen}
            selectedCount={selectedIds.size}
            deleting={deleteMutation.isPending}
            error={deleteMutation.error}
            onOpenChange={setDeleteDialogOpen}
            onConfirm={confirmDeleteSelected}
          />
        </section>
      )}
      {createPortal(
        <BulkSelectionBar
          visible={selectedIds.size > 0}
          selectedCount={selectedIds.size}
          deleting={deleteMutation.isPending}
          onClear={clearSelection}
          onDelete={() => setDeleteDialogOpen(true)}
        />,
        document.body,
      )}
    </PageContainer>
  );
}

function BulkSelectionBar({
  visible,
  selectedCount,
  deleting,
  onClear,
  onDelete,
}: {
  visible: boolean;
  selectedCount: number;
  deleting: boolean;
  onClear: () => void;
  onDelete: () => void;
}) {
  // Bar is always mounted to avoid DOM mount/unmount reflows. Visibility
  // is toggled via opacity + pointer-events so the table never reflows
  // when a checkbox is clicked.
  return (
    <div
      role="region"
      aria-label="Auswahl-Aktionen"
      aria-hidden={!visible}
      style={{
        position: "fixed",
        left: "50%",
        bottom: "1.5rem",
        transform: `translateX(-50%) translateY(${visible ? "0" : "1rem"})`,
        zIndex: 50,
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? "auto" : "none",
        transition: "opacity 180ms ease, transform 180ms ease",
      }}
      className="flex items-center gap-2 rounded-full border border-border bg-surface/95 py-1.5 pl-4 pr-1.5 shadow-lg backdrop-blur"
    >
      <span className="text-sm font-semibold text-foreground whitespace-nowrap">
        {selectedCount} Anfrage{selectedCount === 1 ? "" : "n"} ausgewählt
      </span>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={deleting || !visible}
        onClick={onClear}
      >
        <X className="h-4 w-4" aria-hidden="true" />
        Auswahl aufheben
      </Button>
      <Button
        type="button"
        variant="danger"
        size="sm"
        disabled={deleting || !visible}
        onClick={onDelete}
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
        Löschen
      </Button>
    </div>
  );
}

function DeleteReviewsDialog({
  open,
  selectedCount,
  deleting,
  error,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  selectedCount: number;
  deleting: boolean;
  error: Error | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Anfragen löschen?</DialogTitle>
          <DialogDescription>
            {selectedCount} ausgewählte Anfrage
            {selectedCount === 1 ? "" : "n"} werden dauerhaft aus der
            Review-Übersicht und dem Review-Speicher entfernt.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p className="mb-4 rounded-md border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger">
            {error.message}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={deleting}
            onClick={() => onOpenChange(false)}
          >
            Abbrechen
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={deleting || selectedCount === 0}
            onClick={onConfirm}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {deleting ? "Lösche…" : "Endgültig löschen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
