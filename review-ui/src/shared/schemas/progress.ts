import { z } from "zod";

/**
 * Mirrors `quoting/api/progress_store.py`.
 */

export const stepStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
]);

export const pipelineStepSchema = z
  .object({
    name: z.string(),
    status: stepStatusSchema,
    detail: z.string().default(""),
    updated_at: z.string().nullable().optional(),
  })
  .passthrough();

export const pipelineStatusSchema = z.enum(["running", "completed", "failed"]);

export const pipelineProgressSchema = z
  .object({
    review_id: z.string(),
    status: pipelineStatusSchema,
    current_step: z.string(),
    current_detail: z.string().default(""),
    progress_percent: z.number().min(0).max(100),
    created_at: z.string().nullable().optional(),
    updated_at: z.string(),
    steps: z.array(pipelineStepSchema),
    result: z.record(z.unknown()).nullable().optional(),
    error: z.string().nullable().optional(),
  })
  .passthrough();

export type PipelineProgress = z.infer<typeof pipelineProgressSchema>;
export type PipelineStep = z.infer<typeof pipelineStepSchema>;
