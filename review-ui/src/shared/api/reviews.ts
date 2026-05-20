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
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

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
  original_anfrage: Anfrage | null;
  matches: MatchResult[];
  quotation: Quotation | null;
  manual_overrides: ManualOverride[];
  mail: MailMeta;
  has_draft_pdf: boolean;
  has_final_pdf: boolean;
  requirements_acknowledged: number[];
}

export interface PdfHighlightArea {
  pageIndex: number;
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface PdfHighlightResponse {
  status: string;
  areas: PdfHighlightArea[];
  pageIndex?: number | null;
  matched_text?: string | null;
  message?: string | null;
}

export interface FinalizeInput {
  actor: string;
  filename?: string;
  warning_acknowledged?: boolean;
  exception_reason?: string;
}

const reviewDetailSchema = z.object({
  review_id: z.string(),
  created_at: z.string().nullable().default(null),
  anfrage: anfrageSchema,
  original_anfrage: anfrageSchema.nullable().default(null),
  matches: z.array(matchResultSchema),
  quotation: quotationSchema.nullable(),
  manual_overrides: z.array(manualOverrideSchema).default([]),
  mail: mailMetaSchema,
  has_draft_pdf: z.boolean(),
  has_final_pdf: z.boolean(),
  requirements_acknowledged: z.array(z.number().int()).default([]),
});

const pdfHighlightResponseSchema = z.object({
  status: z.string(),
  areas: z.array(
    z.object({
      pageIndex: z.number().int(),
      left: z.number(),
      top: z.number(),
      width: z.number(),
      height: z.number(),
    }),
  ),
  pageIndex: z.number().int().nullable().optional(),
  matched_text: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
});

/**
 * Backend route templates for review-scoped endpoints.
 *
 * Centralized so a route rename touches only this object; callers compose
 * via `reviewPath(id).status` etc. Each function pre-encodes the review id.
 */
export const reviewPath = (reviewId: string) => {
  const id = encodeURIComponent(reviewId);
  const base = `/api/reviews/${id}`;
  return {
    base,
    status: `${base}/status`,
    anfrage: `${base}/anfrage`,
    overrides: `${base}/overrides`,
    regenerate: `${base}/regenerate`,
    finalize: `${base}/finalize`,
    reset: `${base}/reset`,
    requirementsAck: `${base}/requirements-ack`,
    pdfHighlight: (fileName: string) =>
      `${base}/attachment/${encodeURIComponent(fileName)}/pdf/highlight`,
  };
};

export const reviewsApi = {
  list: async (): Promise<ReviewSummary[]> => {
    const data = await apiClient.get<unknown>("/api/reviews");
    return z.array(reviewSummarySchema).parse(data);
  },

  detail: async (reviewId: string): Promise<ReviewDetail> => {
    const data = await apiClient.get<unknown>(reviewPath(reviewId).base);
    return reviewDetailSchema.parse(data);
  },

  delete: async (reviewId: string): Promise<void> => {
    await apiClient.delete<void>(reviewPath(reviewId).base);
  },

  deleteMany: async (reviewIds: string[]): Promise<void> => {
    await Promise.all(reviewIds.map((reviewId) => reviewsApi.delete(reviewId)));
  },

  status: async (reviewId: string): Promise<PipelineProgress> => {
    const data = await apiClient.get<unknown>(reviewPath(reviewId).status);
    return pipelineProgressSchema.parse(data);
  },

  saveAnfrage: async (reviewId: string, anfrage: Anfrage): Promise<Anfrage> => {
    const data = await apiClient.put<unknown>(reviewPath(reviewId).anfrage, anfrage);
    return anfrageSchema.parse(data);
  },

  saveOverrides: async (
    reviewId: string,
    overrides: ManualOverride[],
  ): Promise<ManualOverride[]> => {
    const data = await apiClient.put<unknown>(reviewPath(reviewId).overrides, overrides);
    return z.array(manualOverrideSchema).parse(data);
  },

  regenerate: async (reviewId: string): Promise<Quotation> => {
    const data = await apiClient.post<unknown>(reviewPath(reviewId).regenerate);
    return quotationSchema.parse(data);
  },

  finalize: async (
    reviewId: string,
    input: FinalizeInput,
  ): Promise<{ final_pdf_path: string }> => {
    const data = await apiClient.post<unknown>(
      reviewPath(reviewId).finalize,
      {
        actor: input.actor,
        ...(input.filename ? { filename: input.filename } : {}),
        ...(input.warning_acknowledged !== undefined
          ? { warning_acknowledged: input.warning_acknowledged }
          : {}),
        ...(input.exception_reason ? { exception_reason: input.exception_reason } : {}),
      },
    );
    return z.object({ final_pdf_path: z.string() }).parse(data);
  },

  reset: async (reviewId: string): Promise<void> => {
    await apiClient.post(reviewPath(reviewId).reset);
  },

  acknowledgeRequirements: async (
    reviewId: string,
    indices: number[],
  ): Promise<number[]> => {
    const data = await apiClient.put<unknown>(
      reviewPath(reviewId).requirementsAck,
      { indices },
    );
    return z
      .object({ indices: z.array(z.number().int()) })
      .parse(data).indices;
  },

  pdfHighlight: async (
    reviewId: string,
    fileName: string,
    target: SourceNavigationTarget,
  ): Promise<PdfHighlightResponse> => {
    const { evidence } = target;
    const data = await apiClient.post<unknown>(
      reviewPath(reviewId).pdfHighlight(fileName),
      {
        source_page: evidence.source_page ?? null,
        source_quote: evidence.source_quote ?? null,
        candidates: target.candidates,
        target_kind: target.targetKind,
      },
    );
    return pdfHighlightResponseSchema.parse(data);
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
