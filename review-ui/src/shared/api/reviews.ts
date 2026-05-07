import { apiClient } from "./client";
import { anfrageSchema, type Anfrage } from "../schemas/anfrage";
import { matchResultSchema, type MatchResult } from "../schemas/matchResult";
import {
  manualOverrideSchema,
  quotationSchema,
  type ManualOverride,
  type Quotation,
} from "../schemas/quotation";
import { pipelineProgressSchema, type PipelineProgress } from "../schemas/progress";
import {
  reviewSummarySchema,
  type ReviewSummary,
} from "@/features/dashboard/schemas/reviewSummary";
import { z } from "zod";

/**
 * Reviews API surface.
 *
 * Each function validates the API response with zod — if the backend
 * ever drifts from the schema we'll see a clean parse error in the
 * affected query, not a cryptic crash deep inside a render.
 */

export interface MailMeta {
  subject: string;
  from: string;
  body: string;
  attachments: Array<{ name: string; contentType?: string; size?: number }>;
}

const mailMetaSchema = z.object({
  subject: z.string().default(""),
  from: z.string().default(""),
  body: z.string().default(""),
  attachments: z
    .array(
      z.object({
        name: z.string(),
        contentType: z.string().optional(),
        size: z.number().optional(),
      }),
    )
    .default([]),
});

export interface ReviewDetail {
  review_id: string;
  created_at: string | null;
  anfrage: Anfrage;
  matches: MatchResult[];
  quotation: Quotation | null;
  manual_overrides: ManualOverride[];
  mail: MailMeta;
  has_draft_pdf: boolean;
  has_final_pdf: boolean;
}

const reviewDetailSchema = z.object({
  review_id: z.string(),
  created_at: z.string().nullable().default(null),
  anfrage: anfrageSchema,
  matches: z.array(matchResultSchema),
  quotation: quotationSchema.nullable(),
  manual_overrides: z.array(manualOverrideSchema).default([]),
  mail: mailMetaSchema,
  has_draft_pdf: z.boolean(),
  has_final_pdf: z.boolean(),
});

export const reviewsApi = {
  list: async (): Promise<ReviewSummary[]> => {
    const data = await apiClient.get<unknown>("/api/reviews");
    return z.array(reviewSummarySchema).parse(data);
  },

  detail: async (reviewId: string): Promise<ReviewDetail> => {
    const data = await apiClient.get<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}`,
    );
    return reviewDetailSchema.parse(data);
  },

  status: async (reviewId: string): Promise<PipelineProgress> => {
    const data = await apiClient.get<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}/status`,
    );
    return pipelineProgressSchema.parse(data);
  },

  saveAnfrage: async (reviewId: string, anfrage: Anfrage): Promise<Anfrage> => {
    const data = await apiClient.put<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}/anfrage`,
      anfrage,
    );
    return anfrageSchema.parse(data);
  },

  saveOverrides: async (
    reviewId: string,
    overrides: ManualOverride[],
  ): Promise<ManualOverride[]> => {
    const data = await apiClient.put<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}/overrides`,
      overrides,
    );
    return z.array(manualOverrideSchema).parse(data);
  },

  regenerate: async (reviewId: string): Promise<Quotation> => {
    const data = await apiClient.post<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}/regenerate`,
    );
    return quotationSchema.parse(data);
  },

  finalize: async (
    reviewId: string,
    actor: string,
    filename?: string,
  ): Promise<{ final_pdf_path: string }> => {
    const data = await apiClient.post<unknown>(
      `/api/reviews/${encodeURIComponent(reviewId)}/finalize`,
      { actor, ...(filename ? { filename } : {}) },
    );
    return z.object({ final_pdf_path: z.string() }).parse(data);
  },

  reset: async (reviewId: string): Promise<void> => {
    await apiClient.post(`/api/reviews/${encodeURIComponent(reviewId)}/reset`);
  },

  upload: async (file: File): Promise<{ review_id: string }> => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE_URL ?? ""}/api/reviews/upload`,
      { method: "POST", body: form },
    );
    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }
    const data = await response.json();
    return z.object({ review_id: z.string() }).parse(data);
  },
};
