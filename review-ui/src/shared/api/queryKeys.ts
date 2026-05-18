export const reviewListQueryKey = ["reviews", "list"] as const;

export const reviewQueryKey = (reviewId: string) =>
  ["reviews", "detail", reviewId] as const;

export const approvalQueryKey = (reviewId: string) =>
  ["reviews", "approval", reviewId] as const;
