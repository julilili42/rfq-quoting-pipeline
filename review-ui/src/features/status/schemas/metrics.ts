import { z } from "zod";

export const tokenUsageSchema = z
  .object({
    input_tokens: z.number().int(),
    output_tokens: z.number().int(),
    total_tokens: z.number().int(),
  })
  .nullable();

export const extractionPathSchema = z.enum(["fast_path", "llm"]).nullable().optional();

export const perReviewMetricSchema = z.object({
  review_id: z.string(),
  subject: z.string(),
  status: z.string().nullable().optional(),
  updated_at: z.string().optional(),
  positions: z.number().int(),
  match_rate: z.number(),
  total_eur: z.number(),
  duration_s: z.number(),
  approval_duration_s: z.number().default(0),
  approved_at: z.string().nullable().optional(),
  token_usage: tokenUsageSchema.optional(),
  extraction_path: extractionPathSchema,
});

export const metricsSchema = z.object({
  total_reviews: z.number().int(),
  completed_reviews: z.number().int(),
  total_positions: z.number().int(),
  total_eur: z.number(),
  avg_duration_s: z.number(),
  avg_approval_duration_s: z.number().default(0),
  avg_match_rate: z.number(),
  total_input_tokens: z.number().int(),
  total_output_tokens: z.number().int(),
  total_tokens: z.number().int(),
  reviews_with_token_data: z.number().int(),
  reviews_with_approval_duration: z.number().int().default(0),
  fast_path_hits: z.number().int().default(0),
  llm_calls: z.number().int().default(0),
  per_review: z.array(perReviewMetricSchema),
});

export type Metrics = z.infer<typeof metricsSchema>;
export type PerReviewMetric = z.infer<typeof perReviewMetricSchema>;
export type TokenUsage = z.infer<typeof tokenUsageSchema>;
