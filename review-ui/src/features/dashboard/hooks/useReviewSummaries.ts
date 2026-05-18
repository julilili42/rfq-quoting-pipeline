import { useQuery } from "@tanstack/react-query";

import { reviewListQueryKey } from "@/shared/api/queryKeys";
import { reviewsApi } from "@/shared/api/reviews";

/**
 * Dashboard list query.
 *
 * Single source of truth — all dashboard sub-components read from the
 * same query so filtering / pagination / insights stay in sync.
 */
export function useReviewSummaries() {
  return useQuery({
    queryKey: reviewListQueryKey,
    queryFn: () => reviewsApi.list(),
    staleTime: 15_000,
  });
}
