import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Inbox, Trash2, X } from "lucide-react";
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
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
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
import type { ReviewSummary } from "./schemas/reviewSummary";

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

function hasManualClarification(review: ReviewSummary): boolean {
  return Boolean(review.escalation?.escalated);
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const { data: reviews, isLoading, isError, error } = useReviewSummaries();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [sortBy, setSortBy] = useState<SortOption>("attention");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!reviews) return [];
    const q = query.trim().toLowerCase();
    const result = reviews.filter((r) => {
      if (status === "manual_clarification") {
        if (!hasManualClarification(r)) return false;
      } else if (status !== "all" && r.status !== status) {
        return false;
      }
      if (!isWithinPreset(r.created_at, datePreset)) return false;
      if (!q) return true;
      return (
        r.subject.toLowerCase().includes(q) ||
        r.sender.toLowerCase().includes(q) ||
        r.customer.toLowerCase().includes(q) ||
        (r.escalation?.reason ?? "").toLowerCase().includes(q)
      );
    });

    return [...result].sort((a, b) => {
      switch (sortBy) {
        case "attention": {
          // Open reviews needing work first (unmatched positions / low match
          // rate rank highest); finished ones sink to the bottom.
          const attentionScore = (r: typeof a) => {
            if (hasManualClarification(r)) return 10000;
            if (r.status === "abgeschlossen") return -1;
            const matched = r.matches_exact + r.matches_fuzzy + r.matches_semantic;
            const rate = r.positions === 0 ? 1 : matched / r.positions;
            return r.matches_no_match * 100 + Math.round((1 - rate) * 50) + 1;
          };
          const diff = attentionScore(b) - attentionScore(a);
          return diff !== 0
            ? diff
            : new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        }
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

  // Bulk approval (fast lane): finalize each selected review. The server
  // gate decides — reviews with blockers are rejected and stay selected so
  // the user can open and fix them. There is no current-user in the app, so
  // the approver name is a persisted preference.
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);
  const [approver, setApprover] = useState(
    () => localStorage.getItem("ek.approverName") ?? "",
  );
  useEffect(() => {
    localStorage.setItem("ek.approverName", approver);
  }, [approver]);

  const approveMutation = useMutation({
    mutationFn: async (input: { reviewIds: string[]; actor: string }) => {
      const results = await Promise.allSettled(
        input.reviewIds.map((id) => reviewsApi.finalize(id, { actor: input.actor })),
      );
      const ok: string[] = [];
      const failed: string[] = [];
      results.forEach((result, i) =>
        (result.status === "fulfilled" ? ok : failed).push(input.reviewIds[i]),
      );
      return { ok, failed };
    },
    onSuccess: ({ ok }) => {
      if (ok.length > 0) {
        setSelectedIds((prev) => {
          const next = new Set(prev);
          ok.forEach((id) => next.delete(id));
          return next;
        });
      }
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });

  const confirmApproveSelected = () => {
    const actor = approver.trim();
    if (!actor || selectedReviewIds.length === 0) return;
    approveMutation.mutate(
      { reviewIds: selectedReviewIds, actor },
      { onSuccess: ({ failed }) => { if (failed.length === 0) setApproveDialogOpen(false); } },
    );
  };

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
          approving={approveMutation.isPending}
          onClear={clearSelection}
          onApprove={() => {
            approveMutation.reset();
            setApproveDialogOpen(true);
          }}
          onDelete={() => setDeleteDialogOpen(true)}
        />,
        document.body,
      )}
      <ApproveReviewsDialog
        open={approveDialogOpen}
        selectedCount={selectedIds.size}
        approver={approver}
        onApproverChange={setApprover}
        pending={approveMutation.isPending}
        approvedCount={approveMutation.data?.ok.length ?? 0}
        failedCount={approveMutation.data?.failed.length ?? 0}
        onOpenChange={setApproveDialogOpen}
        onConfirm={confirmApproveSelected}
      />
    </PageContainer>
  );
}

function BulkSelectionBar({
  visible,
  selectedCount,
  deleting,
  approving,
  onClear,
  onApprove,
  onDelete,
}: {
  visible: boolean;
  selectedCount: number;
  deleting: boolean;
  approving: boolean;
  onClear: () => void;
  onApprove: () => void;
  onDelete: () => void;
}) {
  const busy = deleting || approving;
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
        disabled={busy || !visible}
        onClick={onClear}
      >
        <X className="h-4 w-4" aria-hidden="true" />
        Auswahl aufheben
      </Button>
      <Button
        type="button"
        variant="primary"
        size="sm"
        disabled={busy || !visible}
        onClick={onApprove}
      >
        <Check className="h-4 w-4" aria-hidden="true" />
        Freigeben
      </Button>
      <Button
        type="button"
        variant="danger"
        size="sm"
        disabled={busy || !visible}
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

function ApproveReviewsDialog({
  open,
  selectedCount,
  approver,
  onApproverChange,
  pending,
  approvedCount,
  failedCount,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  selectedCount: number;
  approver: string;
  onApproverChange: (name: string) => void;
  pending: boolean;
  approvedCount: number;
  failedCount: number;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Anfragen freigeben?</DialogTitle>
          <DialogDescription>
            {selectedCount} ausgewählte Anfrage
            {selectedCount === 1 ? "" : "n"} werden freigegeben und als finales
            Angebot erzeugt. Anfragen mit offenen Punkten werden übersprungen
            und bleiben markiert.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label className="text-xs font-semibold text-foreground">
            Freigegeben durch
          </Label>
          <Input
            value={approver}
            onChange={(e) => onApproverChange(e.target.value)}
            placeholder="Vor- und Nachname"
            autoComplete="name"
          />
        </div>

        {failedCount > 0 && (
          <p className="mt-3 rounded-md border border-warning/30 bg-warning-soft px-3 py-2 text-sm text-warning">
            {approvedCount} freigegeben, {failedCount} mit offenen Punkten —
            bitte einzeln öffnen und prüfen.
          </p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={pending}
            onClick={() => onOpenChange(false)}
          >
            {failedCount > 0 ? "Schließen" : "Abbrechen"}
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={pending || selectedCount === 0 || approver.trim().length === 0}
            onClick={onConfirm}
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            {pending ? "Freigabe läuft…" : "Freigeben"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
