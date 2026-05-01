import { REVIEW_API_URL } from "../config";
import type {
  CreateReviewResponse,
  MailSnapshot,
  PipelineProgress,
} from "../types";

export type ProgressCallback = (progress: PipelineProgress) => void;

const DEFAULT_POLL_INTERVAL_MS = 900;
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function withCacheBust(url: string): string {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${Date.now()}`;
}

export async function startReview(
  mail: MailSnapshot,
): Promise<CreateReviewResponse> {
  console.log("Sending mail snapshot to review API:", {
    subject: mail.subject,
    from: mail.from,
    bodyLength: mail.body.length,
    attachments: mail.attachments.map((a) => ({
      name: a.name,
      contentType: a.contentType,
      size: a.size,
      base64Length: a.contentBase64?.length || 0,
    })),
  });

  const response = await fetch(REVIEW_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mail),
  });

  const text = await response.text();
  console.log("Review API status:", response.status);
  console.log("Review API raw response:", text);

  if (!response.ok) {
    throw new Error(`Review API failed (${response.status}): ${text}`);
  }
  return JSON.parse(text) as CreateReviewResponse;
}

export async function getReviewStatus(
  review: CreateReviewResponse,
): Promise<PipelineProgress> {
  const statusUrl =
    review.status_url ?? `${REVIEW_API_URL}/${review.review_id}/status`;
  const response = await fetch(withCacheBust(statusUrl), {
    method: "GET",
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Status check failed (${response.status}): ${text}`);
  }
  return JSON.parse(text) as PipelineProgress;
}

/**
 * Approval record returned by the API.
 *
 * `state` follows the backend's approval state machine:
 *   draft_generated → reviewed → approved → ready_to_send
 *
 * We only care about `approved` / `ready_to_send` for unlocking the
 * "Angebotsmail erstellen" action in the plugin.
 */
export type ApprovalRecord = {
  state:
    | "draft_generated"
    | "reviewed"
    | "approved"
    | "ready_to_send";
  approved_by?: string | null;
  approved_at?: string | null;
  final_pdf_path?: string | null;
};

export async function getApprovalState(
  reviewId: string,
): Promise<ApprovalRecord> {
  const url = `${REVIEW_API_URL}/${reviewId}/approval`;
  const response = await fetch(withCacheBust(url), { method: "GET" });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Approval check failed (${response.status}): ${text}`);
  }
  return JSON.parse(text) as ApprovalRecord;
}

export function isApproved(record: ApprovalRecord): boolean {
  return record.state === "approved" || record.state === "ready_to_send";
}

export async function pollReviewUntilComplete(
  review: CreateReviewResponse,
  onProgress?: ProgressCallback,
  options?: {
    intervalMs?: number;
    timeoutMs?: number;
  },
): Promise<CreateReviewResponse> {
  const intervalMs = options?.intervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const startedAt = Date.now();

  while (true) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(
        `Pipeline timeout after ${Math.round(timeoutMs / 1000)} seconds`,
      );
    }

    const progress = await getReviewStatus(review);
    onProgress?.(progress);

    if (progress.status === "failed") {
      throw new Error(progress.error || "Pipeline failed");
    }

    if (progress.status === "completed") {
      const completed = progress.result ?? review;
      await checkPdfUrl(completed);
      return {
        ...review,
        ...completed,
        status: "completed",
        progress,
      };
    }

    await sleep(intervalMs);
  }
}

export async function createReview(
  mail: MailSnapshot,
  onProgress?: ProgressCallback,
): Promise<CreateReviewResponse> {
  const started = await startReview(mail);
  return pollReviewUntilComplete(started, onProgress);
}

async function checkPdfUrl(result: CreateReviewResponse): Promise<void> {
  try {
    const pdfCheck = await fetch(withCacheBust(result.draft_pdf_url), {
      method: "GET",
    });
    console.log("PDF check status:", pdfCheck.status);
    console.log(
      "PDF check content-type:",
      pdfCheck.headers.get("content-type"),
    );
    if (!pdfCheck.ok) {
      throw new Error(`PDF URL check failed with status ${pdfCheck.status}`);
    }
  } catch (error) {
    console.error("PDF URL check failed:", error);
    throw new Error(
      `Review wurde erstellt, aber PDF-URL ist aus dem Add-in nicht erreichbar: ${String(error)}`,
    );
  }
}
