import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/shared/api/client";

const checkResultSchema = z.object({
  name: z.string(),
  status: z.enum(["ok", "warning", "error"]),
  detail: z.string(),
});

export const llmProbeResultSchema = z.object({
  status: z.enum(["ok", "error"]),
  provider: z.string(),
  model: z.string(),
  checked_at: z.string(),
  latency_ms: z.number().int(),
  detail: z.string(),
  response_preview: z.string().nullable().optional(),
  error_type: z.string().nullable().optional(),
  usage: z
    .object({
      input_tokens: z.number().int(),
      output_tokens: z.number().int(),
      total_tokens: z.number().int(),
    })
    .nullable()
    .optional(),
});

export const pipelineFailureSchema = z.object({
  review_id: z.string(),
  subject: z.string(),
  sender: z.string(),
  current_step: z.string(),
  error: z.string(),
  updated_at: z.string(),
  progress_percent: z.number().int(),
});

export const pipelineFailureSummarySchema = z.object({
  total_failed: z.number().int(),
  recent: z.array(pipelineFailureSchema),
});

export const stammdatenQualitySchema = z.object({
  path: z.string(),
  total_rows: z.number().int(),
  file_size_kb: z.number().int(),
  last_modified: z.string(),
  duplicate_article_numbers: z.number().int(),
  missing_article_numbers: z.number().int(),
  missing_descriptions: z.number().int(),
  zero_or_missing_prices: z.number().int(),
  invalid_price_ranges: z.number().int(),
  single_offer_articles: z.number().int(),
  missing_materials: z.number().int(),
  missing_dimensions: z.number().int(),
  sample_duplicate_articles: z.array(z.string()),
  sample_zero_price_articles: z.array(z.string()),
});

export const debugInfoSchema = z.object({
  overall: z.enum(["ok", "warning", "error"]),
  checks: z.array(checkResultSchema),
  llm_provider: z.string(),
  checked_at: z.string(),
  pipeline_failures: pipelineFailureSummarySchema,
  stammdaten_quality: stammdatenQualitySchema.nullable(),
});

export type CheckResult = z.infer<typeof checkResultSchema>;
export type DebugInfo = z.infer<typeof debugInfoSchema>;
export type LlmProbeResult = z.infer<typeof llmProbeResultSchema>;
export type PipelineFailure = z.infer<typeof pipelineFailureSchema>;
export type PipelineFailureSummary = z.infer<typeof pipelineFailureSummarySchema>;
export type StammdatenQuality = z.infer<typeof stammdatenQualitySchema>;

export function useDebug() {
  return useQuery({
    queryKey: ["debug"],
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/debug");
      return debugInfoSchema.parse(data);
    },
    staleTime: 0,
    retry: 1,
  });
}

export function useLlmProbe() {
  return useMutation({
    mutationFn: async () => {
      const data = await apiClient.post<unknown>("/api/debug/llm");
      return llmProbeResultSchema.parse(data);
    },
  });
}
