import { API_BASE_URL, REVIEW_API_URL } from "../config";
import type {
  CreateReviewResponse,
  MailSnapshot,
  PipelineProgress,
} from "../types";
import { withCacheBust } from "../utils";

export type ProgressCallback = (progress: PipelineProgress) => void;

const DEFAULT_POLL_INTERVAL_MS = 900;
const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Thrown when the backend reports that a review id no longer exists.
 * Callers should treat this as a signal to drop the locally cached
 * workflow entry — the underlying review was deleted server-side and
 * polling will never succeed.
 */
export class ReviewNotFoundError extends Error {
  readonly reviewId: string;

  constructor(reviewId: string) {
    super(`Review ${reviewId} not found`);
    this.name = "ReviewNotFoundError";
    this.reviewId = reviewId;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function startReview(
  mail: MailSnapshot,
  outlookItemId?: string,
): Promise<CreateReviewResponse> {
  const body = outlookItemId
    ? { ...mail, outlook_item_id: outlookItemId }
    : mail;
  const response = await fetch(REVIEW_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const text = await response.text();
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
  if (response.status === 404) {
    throw new ReviewNotFoundError(review.review_id);
  }
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
  if (response.status === 404) {
    throw new ReviewNotFoundError(reviewId);
  }
  if (!response.ok) {
    throw new Error(`Approval check failed (${response.status}): ${text}`);
  }
  return JSON.parse(text) as ApprovalRecord;
}

export function isApproved(record: ApprovalRecord): boolean {
  return record.state === "approved" || record.state === "ready_to_send";
}

/**
 * Look up the review currently bound to an Outlook itemId.
 *
 * Returns the server's compact status payload. Throws
 * ReviewNotFoundError when no review is bound — callers should treat
 * that as "this mail is in the `new` workflow state".
 */
export async function getOutlookItemStatus(
  outlookItemId: string,
): Promise<import("../serverWorkflow").OutlookItemStatus> {
  const query = new URLSearchParams({ outlook_item_id: outlookItemId });
  const url = `${REVIEW_API_URL}/by-outlook-item?${query.toString()}`;
  const response = await fetch(withCacheBust(url), { method: "GET" });
  const text = await response.text();
  if (response.status === 404) {
    throw new ReviewNotFoundError(outlookItemId);
  }
  if (!response.ok) {
    throw new Error(`Outlook-item status failed (${response.status}): ${text}`);
  }
  return JSON.parse(text) as import("../serverWorkflow").OutlookItemStatus;
}

export async function markReviewOpened(reviewId: string): Promise<void> {
  const url = `${REVIEW_API_URL}/${reviewId}/mark-opened`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`mark-opened failed (${response.status}): ${text}`);
  }
}

export async function detachOutlookItem(outlookItemId: string): Promise<void> {
  const query = new URLSearchParams({ outlook_item_id: outlookItemId });
  const url = `${REVIEW_API_URL}/by-outlook-item/detach?${query.toString()}`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok && response.status !== 404) {
    const text = await response.text();
    throw new Error(`detach failed (${response.status}): ${text}`);
  }
}

export async function transitionApprovalToReadyToSend(
  reviewId: string,
): Promise<void> {
  const url = `${REVIEW_API_URL}/${reviewId}/approval`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target: "ready_to_send" }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`ready_to_send transition failed (${response.status}): ${text}`);
  }
}

export type MailTemplateSettings = {
  email_subject_template: string;
  email_body_template: string;
  company_name: string;
  body_source: "template" | "llm";
};

function extractEmailAddress(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const bracketMatch = value.match(/<([^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>/);
  if (bracketMatch?.[1]) return bracketMatch[1].trim();
  const plainMatch = value.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  return plainMatch?.[0]?.trim() ?? null;
}

export async function getMailSettings(reviewId: string): Promise<{ kundenFirma: string | null; recipientEmail: string | null; templates: MailTemplateSettings }> {
  const [detailRes, settingsRes] = await Promise.all([
    fetch(`${REVIEW_API_URL}/${reviewId}`, { method: "GET" }),
    fetch(`${API_BASE_URL}/api/settings`, { method: "GET" }),
  ]);

  let kundenFirma: string | null = null;
  let recipientEmail: string | null = null;
  if (detailRes.ok) {
    try {
      const detail = JSON.parse(await detailRes.text());
      kundenFirma = detail?.anfrage?.kunde_firma ?? null;
      recipientEmail =
        extractEmailAddress(detail?.anfrage?.kunde_email) ??
        extractEmailAddress(detail?.mail?.from);
    } catch { /* ignore */ }
  }

  const defaults: MailTemplateSettings = {
    email_subject_template: "Angebot zu Ihrer Anfrage: [Betreff]",
    email_body_template: "<p>Sehr geehrte Damen und Herren,</p><p>vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot.</p><p>Mit freundlichen Grüßen<br/>[Absender]</p>",
    company_name: "",
    body_source: "template",
  };

  let useLlmBody = false;
  if (settingsRes.ok) {
    try {
      const s = JSON.parse(await settingsRes.text());
      defaults.email_subject_template = s?.workflow?.email_subject_template ?? defaults.email_subject_template;
      defaults.email_body_template = s?.workflow?.email_body_template ?? defaults.email_body_template;
      defaults.company_name = s?.company?.contact_person || s?.company?.company_name || "";
      useLlmBody = Boolean(s?.workflow?.use_llm_email_body);
    } catch { /* ignore */ }
  }

  if (useLlmBody) {
    try {
      const replyRes = await fetch(`${REVIEW_API_URL}/${reviewId}/reply-body`, { method: "GET" });
      if (replyRes.ok) {
        const body = JSON.parse(await replyRes.text());
        if (typeof body?.body === "string" && body.body.trim().length > 0) {
          defaults.email_body_template = body.body;
          defaults.body_source = "llm";
        }
      }
    } catch { /* fallback to static template */ }
  }

  return { kundenFirma, recipientEmail, templates: defaults };
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
      await checkPdfUrl(completed).catch(() => {
        /* PDF transiently unreachable from add-in — proceed anyway */
      });
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

async function checkPdfUrl(result: CreateReviewResponse): Promise<void> {
  try {
    const pdfCheck = await fetch(withCacheBust(result.draft_pdf_url), {
      method: "GET",
    });
    if (!pdfCheck.ok) {
      throw new Error(`PDF URL check failed with status ${pdfCheck.status}`);
    }
  } catch (error) {
    throw new Error(
      `Review wurde erstellt, aber PDF-URL ist aus dem Add-in nicht erreichbar: ${String(error)}`,
      { cause: error },
    );
  }
}
