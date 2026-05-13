import { API_BASE_URL, REVIEW_API_URL } from "../config";
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
  const response = await fetch(REVIEW_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mail),
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

export type MailTemplateSettings = {
  email_subject_template: string;
  email_body_template: string;
  company_name: string;
};

export async function getMailSettings(reviewId: string): Promise<{ kundenFirma: string | null; templates: MailTemplateSettings }> {
  const [detailRes, settingsRes] = await Promise.all([
    fetch(`${REVIEW_API_URL}/${reviewId}`, { method: "GET" }),
    fetch(`${API_BASE_URL}/api/settings`, { method: "GET" }),
  ]);

  let kundenFirma: string | null = null;
  if (detailRes.ok) {
    try {
      const detail = JSON.parse(await detailRes.text());
      kundenFirma = detail?.anfrage?.kunde_firma ?? null;
    } catch { /* ignore */ }
  }

  const defaults: MailTemplateSettings = {
    email_subject_template: "Angebot zu Ihrer Anfrage: [Betreff]",
    email_body_template: "<p>Sehr geehrte Damen und Herren,</p><p>vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot.</p><p>Mit freundlichen Grüßen<br/>[Absender]</p>",
    company_name: "",
  };

  if (settingsRes.ok) {
    try {
      const s = JSON.parse(await settingsRes.text());
      defaults.email_subject_template = s?.workflow?.email_subject_template ?? defaults.email_subject_template;
      defaults.email_body_template = s?.workflow?.email_body_template ?? defaults.email_body_template;
      defaults.company_name = s?.company?.company_name ?? "";
    } catch { /* ignore */ }
  }

  return { kundenFirma, templates: defaults };
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
    if (!pdfCheck.ok) {
      throw new Error(`PDF URL check failed with status ${pdfCheck.status}`);
    }
  } catch (error) {
    throw new Error(
      `Review wurde erstellt, aber PDF-URL ist aus dem Add-in nicht erreichbar: ${String(error)}`,
    );
  }
}
