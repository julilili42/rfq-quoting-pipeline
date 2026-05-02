import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { stammdatenApi } from "@/shared/api/stammdaten";

import { reviewQueryKey } from "./useReview";

/**
 * Live stammdaten search.
 *
 * The query key includes the actual search term so React Query caches
 * one entry per term — useful when the user types, deletes a char,
 * and re-types it.
 */
export function useStammdatenSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: ["stammdaten", "search", query],
    queryFn: () => stammdatenApi.search(query, 25),
    enabled,
    // Keep results fresh for 60s; stammdaten don't change between
    // clicks of the search button.
    staleTime: 60_000,
  });
}

/**
 * Pin a position to a stammdaten article — invalidates the matching
 * review-detail query so the new match shows up immediately.
 */
export function useMatchOverride(reviewId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ posNr, artikelNr }: { posNr: number; artikelNr: string }) => {
      if (!reviewId) throw new Error("reviewId is required");
      return stammdatenApi.overrideMatch(reviewId, posNr, artikelNr);
    },
    onSuccess: () => {
      if (!reviewId) return;
      queryClient.invalidateQueries({ queryKey: reviewQueryKey(reviewId) });
    },
  });
}
