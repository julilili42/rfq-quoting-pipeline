import React, { useEffect } from "react";
import { Outlet, useParams, useSearchParams } from "react-router-dom";

import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { isApproved } from "@/shared/schemas/approval";

import { PipelineProgress } from "./components/PipelineProgress";
import { ReviewHero } from "./components/ReviewHero";
import { StepIndicator } from "./components/StepIndicator";
import { useApproval } from "./hooks/useApproval";
import { useReview } from "./hooks/useReview";
import { useReviewStatus } from "./hooks/useReviewStatus";
import { useReviewUiStore } from "./stores/reviewUiStore";

class StepErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[StepErrorBoundary]", error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <PageContainer>
          <ErrorState
            title="Fehler beim Rendern des Schritts"
            error={this.state.error}
            action={
              <button
                className="mt-2 text-xs underline"
                onClick={() => this.setState({ error: null })}
              >
                Erneut versuchen
              </button>
            }
          />
        </PageContainer>
      );
    }
    return this.props.children;
  }
}

/**
 * Review detail layout.
 *
 * Acts as a composition root for the two review steps:
 * - Hero and step indicator render once above the active step
 * - The active step renders into the <Outlet/>, fed by data from `useReview`
 *
 * If the pipeline is still running we suppress all editor chrome and
 * just show the progress card — same pattern as the Streamlit version.
 */
export function ReviewDetailPage() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const [searchParams] = useSearchParams();
  const focusMode = searchParams.get("focus") === "1";

  const setActiveReview = useReviewUiStore((s) => s.setActiveReview);
  const syncReviewChanges = useReviewUiStore((s) => s.syncReviewChanges);

  // Reset per-review UI state whenever we land on a different review.
  useEffect(() => {
    setActiveReview(reviewId ?? null);
    return () => setActiveReview(null);
  }, [reviewId, setActiveReview]);

  const review = useReview(reviewId);
  const status = useReviewStatus(reviewId);
  const approval = useApproval(reviewId);
  const detail = review.data;

  useEffect(() => {
    if (!detail) return;
    syncReviewChanges(
      detail.original_anfrage,
      detail.anfrage,
      detail.manual_overrides,
    );
  }, [
    detail,
    syncReviewChanges,
  ]);

  const isPipelineRunning =
    status.data?.status === "running" || status.data?.status === "failed";

  if (!reviewId) {
    return (
      <PageContainer>
        <ErrorState error="Keine Review-ID angegeben." />
      </PageContainer>
    );
  }

  if (review.isLoading) {
    return (
      <PageContainer>
        <LoadingState label="Lade Review…" />
      </PageContainer>
    );
  }

  if (review.isError) {
    return (
      <PageContainer>
        <ErrorState
          title="Review konnte nicht geladen werden"
          error={review.error}
        />
      </PageContainer>
    );
  }

  if (!detail) {
    return (
      <PageContainer>
        <ErrorState error="Review-Daten unvollständig." />
      </PageContainer>
    );
  }

  const approved = isApproved(approval.data);
  const approvedAt = approved ? (approval.data?.approved_at ?? null) : null;

  // Vollbild — only meaningful for the approval step. The step itself
  // is responsible for rendering the focus toolbar.
  if (focusMode) {
    return (
      <StepErrorBoundary>
        <Outlet context={{ detail, focusMode: true }} />
      </StepErrorBoundary>
    );
  }

  if (isPipelineRunning && status.data) {
    return (
      <PageContainer>
        <ReviewHero
          reviewId={reviewId}
          createdAt={detail?.created_at ?? null}
          isApproved={approved}
          approvedAt={approvedAt}
        />
        <PipelineProgress progress={status.data} />
      </PageContainer>
    );
  }

  return (
    <PageContainer wide>
      <ReviewHero
        reviewId={reviewId}
        createdAt={detail.created_at}
        isApproved={approved}
        approvedAt={approvedAt}
      />
      <div className="mb-8">
        <StepIndicator />
      </div>
      <StepErrorBoundary>
        <Outlet context={{ detail, focusMode: false }} />
      </StepErrorBoundary>
    </PageContainer>
  );
}

/**
 * Typed Outlet context — every step reads the loaded detail from here
 * via `useOutletContext<ReviewDetailContext>()`.
 */
export interface ReviewDetailContext {
  detail: NonNullable<ReturnType<typeof useReview>["data"]>;
  focusMode: boolean;
}
