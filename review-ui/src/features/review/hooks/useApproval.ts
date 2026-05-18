import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { approvalApi, type ApprovalTransitionInput } from "@/shared/api/approval";
import {
  approvalQueryKey,
  reviewListQueryKey,
  reviewQueryKey,
} from "@/shared/api/queryKeys";

export { approvalQueryKey };

export function useApproval(reviewId: string | undefined) {
  return useQuery({
    queryKey: approvalQueryKey(reviewId ?? ""),
    queryFn: () => approvalApi.get(reviewId!),
    enabled: Boolean(reviewId),
    staleTime: 5_000,
  });
}

/**
 * Mutate approval state.
 *
 * Invalidates the matching `useReview` query alongside its own — when
 * approval flips, the detail page also needs to know about the new
 * `final_pdf_path`.
 */
export function useApprovalTransition(reviewId: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ApprovalTransitionInput) => {
      if (!reviewId) throw new Error("reviewId is required");
      return approvalApi.transition(reviewId, input);
    },
    onSuccess: () => {
      if (!reviewId) return;
      queryClient.invalidateQueries({ queryKey: approvalQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewQueryKey(reviewId) });
      queryClient.invalidateQueries({ queryKey: reviewListQueryKey });
    },
  });
}
