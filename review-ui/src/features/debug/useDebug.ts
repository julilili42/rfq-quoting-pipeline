import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/shared/api/client";

const checkResultSchema = z.object({
  name: z.string(),
  status: z.enum(["ok", "warning", "error"]),
  detail: z.string(),
});

export const debugInfoSchema = z.object({
  overall: z.enum(["ok", "warning", "error"]),
  checks: z.array(checkResultSchema),
  llm_provider: z.string(),
  checked_at: z.string(),
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

export type CheckResult = z.infer<typeof checkResultSchema>;
export type DebugInfo = z.infer<typeof debugInfoSchema>;
export type LlmProbeResult = z.infer<typeof llmProbeResultSchema>;

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
