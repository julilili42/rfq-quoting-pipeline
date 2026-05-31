import { z } from "zod";

/**
 * Mirrors `quoting/ui/review_ui/review_loader.py::ReviewSummary`.
 *
 * Response shape of the new `GET /api/reviews` endpoint. Datetime
 * values are ISO 8601 strings.
 */

export const reviewStatusSchema = z.enum([
  "in_arbeit",
  "pdf_bereit",
  "abgeschlossen",
]);

export type ReviewStatus = z.infer<typeof reviewStatusSchema>;

export const reviewEscalationSchema = z.object({
  escalated: z.boolean(),
  reason: z.string(),
  actor: z.string().nullable().optional(),
  at: z.string(),
});

export const reviewSummarySchema = z.object({
  review_id: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  subject: z.string(),
  sender: z.string(),
  customer: z.string().default(""),
  positions: z.number().int(),
  confidence_high: z.number().int(),
  confidence_medium: z.number().int(),
  confidence_low: z.number().int(),
  matches_exact: z.number().int(),
  matches_fuzzy: z.number().int(),
  matches_semantic: z.number().int(),
  matches_no_match: z.number().int(),
  total_eur: z.number(),
  currency: z.string(),
  status: reviewStatusSchema,
  has_pdf: z.boolean(),
  manual_overrides_count: z.number().int(),
  escalation: reviewEscalationSchema.nullable().default(null),
  extracted_articles: z.array(z.string()).default([]),
});

export type ReviewSummary = z.infer<typeof reviewSummarySchema>;

/* Computed helpers — derived in the UI, not by the backend. */
export function matchedCount(s: ReviewSummary): number {
  return s.matches_exact + s.matches_fuzzy + s.matches_semantic;
}

export function matchRate(s: ReviewSummary): number {
  return s.positions === 0 ? 0 : matchedCount(s) / s.positions;
}
