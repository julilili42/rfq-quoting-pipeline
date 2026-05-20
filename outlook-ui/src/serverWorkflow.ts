/**
 * Server-derived workflow state for a single Outlook mail.
 *
 * Replaces the previous localStorage-backed state machine. The Outlook
 * itemId is sent to the backend on review creation; subsequent loads
 * query `/api/reviews/by-outlook-item/{id}` to recover the current
 * state. The UI's `MailWorkflowState` is now a pure function of:
 *
 *   - whether a review is bound to this itemId,
 *   - the backend's pipeline `progress.status`,
 *   - the backend's `approval.state`,
 *   - whether `opened_at` has been recorded.
 *
 * State machine, mirroring what the old localStorage record produced:
 *
 *   no review                                                → new
 *   progress.status === "running"                            → review_running
 *   progress.status === "completed" && opened_at == null     → review_created
 *   progress.status === "completed" && opened_at != null
 *     && approval.state in {draft_generated, reviewed}       → review_opened
 *   approval.state === "approved"                            → approved
 *   approval.state === "ready_to_send"                       → quote_sent
 */

import type { MailSnapshot, PipelineProgressStatus } from "./types";

export type MailWorkflowState =
  | "new"
  | "review_running"
  | "review_created"
  | "review_opened"
  | "approved"
  | "quote_sent";

export type ApprovalStateString =
  | "draft_generated"
  | "reviewed"
  | "approved"
  | "ready_to_send";

/** Compact server payload returned by GET /api/reviews/by-outlook-item/{id}. */
export type OutlookItemStatus = {
  review_id: string;
  subject: string;
  sender: string;
  created_at: string | null;
  approval_state: ApprovalStateString;
  progress_status: PipelineProgressStatus | null;
  opened_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  sent_at: string | null;
  final_pdf_filename: string | null;
  kunden_firma: string | null;
  review_url: string;
};

/**
 * View-model the components consume. Everything in here is derived from
 * server state — there is no client-side persistence. The shape is kept
 * close to the previous `MailWorkflow` so WorkflowCard/Steps need only
 * minimal changes.
 */
export type MailWorkflow = {
  mailId: string;
  state: MailWorkflowState;
  reviewId?: string;
  subject: string;
  sender: string;
  reviewCreatedAt?: string;
  reviewOpenedAt?: string;
  approvedAt?: string;
  approvedBy?: string;
  finalPdfFilename?: string;
  kundenFirma?: string;
  quoteSentAt?: string;
  reviewUrl?: string;
};

export function deriveMailId(item: any, snapshot: MailSnapshot): string {
  if (item?.itemId) return String(item.itemId);
  const seed = `${snapshot.subject}|${snapshot.from}|${snapshot.attachments
    .map((a) => `${a.name}:${a.size}`)
    .join(",")}`;
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  return `local_${Math.abs(hash).toString(36)}`;
}

export function deriveWorkflowState(
  status: OutlookItemStatus,
): MailWorkflowState {
  if (status.approval_state === "ready_to_send") return "quote_sent";
  if (status.approval_state === "approved") return "approved";
  if (status.progress_status === "running") return "review_running";
  // Pipeline failures are surfaced by the WorkflowCard's progress banner;
  // for the high-level state we keep the user in "review_running" so they
  // see the error context and can reset.
  if (status.progress_status === "failed") return "review_running";
  if (status.opened_at) return "review_opened";
  return "review_created";
}

export function buildWorkflowFromStatus(
  mailId: string,
  status: OutlookItemStatus,
): MailWorkflow {
  return {
    mailId,
    state: deriveWorkflowState(status),
    reviewId: status.review_id,
    subject: status.subject,
    sender: status.sender,
    reviewCreatedAt: status.created_at ?? undefined,
    reviewOpenedAt: status.opened_at ?? undefined,
    approvedAt: status.approved_at ?? undefined,
    approvedBy: status.approved_by ?? undefined,
    finalPdfFilename: status.final_pdf_filename ?? undefined,
    kundenFirma: status.kunden_firma ?? undefined,
    quoteSentAt: status.sent_at ?? undefined,
    reviewUrl: status.review_url,
  };
}
