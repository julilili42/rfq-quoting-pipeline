import { useMutation, useQueryClient } from "@tanstack/react-query";

import { reviewsApi } from "@/shared/api/reviews";
import type { Anfrage } from "@/shared/schemas/anfrage";
import type { ManualOverride } from "@/shared/schemas/quotation";

import {
  approvalQueryKey,
  reviewListQueryKey,
  reviewQueryKey,
} from "@/shared/api/queryKeys";

/**
 * Persist edits + rebuild draft PDF.
 *
 * The Streamlit UI's `maybe_auto_refresh` / `rebuild_quotation_pdf`
 * pair becomes two atomic API calls here — `saveAnfrage` and
 * `regenerate`. Wrapping them in one mutation keeps the UI optimistic
 * and gives us a single loading state to bind buttons to.
 */
export function useSaveAndRegenerate(reviewId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      anfrage?: Anfrage;
      overrides?: ManualOverride[];
    }) => {
      if (!reviewId) throw new Error("reviewId is required");
      if (input.anfrage) {
        await reviewsApi.saveAnfrage(reviewId, input.anfrage);
      }
      if (input.overrides) {
        await reviewsApi.saveOverrides(reviewId, input.overrides);
      }
      return reviewsApi.regenerate(reviewId);
    },
    onSuccess: () => {
      if (!reviewId) return;
      queryClient.invalidateQueries({ queryKey: reviewQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: approvalQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });
}

/**
 * Build the final PDF and flip approval state in one call.
 */
export function useFinalize(reviewId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actor, filename }: { actor: string; filename?: string }) => {
      if (!reviewId) throw new Error("reviewId is required");
      return reviewsApi.finalize(reviewId, actor, filename);
    },
    onSuccess: () => {
      if (!reviewId) return;
      queryClient.invalidateQueries({ queryKey: reviewQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: approvalQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });
}

export function useResetReview(reviewId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => {
      if (!reviewId) throw new Error("reviewId is required");
      return reviewsApi.reset(reviewId);
    },
    onSuccess: () => {
      if (!reviewId) return;
      queryClient.invalidateQueries({ queryKey: reviewQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: approvalQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });
}
