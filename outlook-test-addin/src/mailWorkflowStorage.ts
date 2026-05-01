/**
 * Per-mail workflow state, persisted in localStorage.
 *
 * Each Outlook item gets its own workflow record. The plugin renders
 * exactly one card based on the current state.
 *
 * State machine:
 *
 *   new
 *    │
 *    │ [Review erstellen]
 *    ▼
 *   review_running
 *    │
 *    │ [Pipeline completed]
 *    ▼
 *   review_created
 *    │
 *    │ [Review-UI öffnen]
 *    ▼
 *   review_opened
 *    │
 *    │ [User klickt "Freigeben" in der Review-UI]
 *    │ [Plugin pollt /approval-Endpoint]
 *    ▼
 *   approved
 *    │
 *    │ [Angebotsmail erstellen]
 *    ▼
 *   quote_sent
 *
 * Vor dem `approved`-Schritt darf der "Angebotsmail erstellen"-Button
 * nicht klickbar sein — sonst landet ein Draft mit rotem KI-Warnhinweis
 * beim Kunden.
 */

import type { CreateReviewResponse, MailSnapshot } from "./types";

export type MailWorkflowState =
  | "new"
  | "review_running"
  | "review_created"
  | "review_opened"
  | "approved"
  | "quote_sent";

export type MailWorkflow = {
  mailId: string;
  subject: string;
  sender: string;
  state: MailWorkflowState;
  review?: CreateReviewResponse;
  reviewCreatedAt?: string;
  reviewOpenedAt?: string;
  approvedAt?: string;
  approvedBy?: string;
  finalPdfFilename?: string;
  quoteSentAt?: string;
  updatedAt: string;
};

const STORAGE_KEY = "quoting.mailWorkflows.v3";
const LEGACY_KEYS = ["quoting.mailWorkflows.v2", "quoting.pendingReview.v1"];

type Store = Record<string, MailWorkflow>;

function readStore(): Store {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function writeStore(store: Store): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* Quota exceeded or storage disabled — current action still works. */
  }
}

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

export function getWorkflow(mailId: string): MailWorkflow | null {
  return readStore()[mailId] ?? null;
}

export function listWorkflows(): MailWorkflow[] {
  return Object.values(readStore()).sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
}

export function upsertWorkflow(
  mailId: string,
  patch: Omit<Partial<MailWorkflow>, "mailId">,
): MailWorkflow {
  const store = readStore();
  const now = new Date().toISOString();
  const existing: MailWorkflow = store[mailId] ?? {
    mailId,
    subject: "",
    sender: "",
    state: "new",
    updatedAt: now,
  };
  const merged: MailWorkflow = {
    ...existing,
    ...patch,
    mailId,
    updatedAt: now,
  };
  store[mailId] = merged;
  writeStore(store);
  return merged;
}

export function deleteWorkflow(mailId: string): void {
  const store = readStore();
  delete store[mailId];
  writeStore(store);
}

export function maybeMigrateLegacy(currentMailId: string): void {
  // v2 → v3: same shape, just bump the key. Older clients used "v2"
  // without an `approved` state; the data is still valid, we just copy
  // it forward and let the polling logic upgrade workflows as needed.
  try {
    const v2 = window.localStorage.getItem("quoting.mailWorkflows.v2");
    if (v2 && !window.localStorage.getItem(STORAGE_KEY)) {
      window.localStorage.setItem(STORAGE_KEY, v2);
    }
  } catch {
    /* ignore */
  }

  // legacy v1 (single pending review)
  try {
    const raw = window.localStorage.getItem("quoting.pendingReview.v1");
    if (!raw) return;
    const legacy = JSON.parse(raw);
    const review: CreateReviewResponse | undefined = legacy?.review;
    if (review?.review_id) {
      const store = readStore();
      if (!store[currentMailId]) {
        store[currentMailId] = {
          mailId: currentMailId,
          subject: legacy.mailSubject ?? "",
          sender: legacy.sender ?? "",
          state: "review_created",
          review,
          reviewCreatedAt: legacy.createdAt ?? new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        writeStore(store);
      }
    }
  } catch {
    /* Ignore malformed legacy state. */
  }

  // Sweep all old keys so we don't keep re-importing them.
  for (const key of LEGACY_KEYS) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  }
}
