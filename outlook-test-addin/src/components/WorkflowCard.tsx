/**
 * WorkflowCard — the main action card in the plugin body.
 */

import type { MailSnapshot } from "../types";
import type {
  MailWorkflow,
  MailWorkflowState,
} from "../mailWorkflowStorage";
import {
  CheckIcon,
  ClockIcon,
  ExternalIcon,
  RefreshIcon,
  SendIcon,
  SparkIcon,
  TrashIcon,
} from "./Icons";

type WorkflowCardProps = {
  workflow: MailWorkflow | null;
  snapshot: MailSnapshot | null;
  isOutlook: boolean;
  loading: boolean;
  onCreateReview: () => void;
  onOpenReview: () => void;
  onCreateDraftMail: () => void;
  onResetWorkflow: () => void;
  onReloadMail: () => void;
};

function formatDate(iso?: string): string {
  if (!iso) return "—";

  const d = new Date(iso);

  if (Number.isNaN(d.getTime())) return iso;

  return d.toLocaleString("de-DE", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function deriveState(workflow: MailWorkflow | null): MailWorkflowState {
  return workflow?.state ?? "new";
}

function StatusPill({ state }: { state: MailWorkflowState }) {
  const meta: Record<MailWorkflowState, { label: string; cls: string }> = {
    new: {
      label: "Neue Anfrage",
      cls: "pill pill-neutral",
    },
    review_running: {
      label: "Pipeline läuft",
      cls: "pill pill-info",
    },
    review_created: {
      label: "Review bereit",
      cls: "pill pill-info",
    },
    review_opened: {
      label: "In Bearbeitung",
      cls: "pill pill-info",
    },
    quote_sent: {
      label: "Angebot versendet",
      cls: "pill pill-success",
    },
  };

  const { label, cls } = meta[state];

  return (
    <span className={cls}>
      <span className="pill-dot" />
      {label}
    </span>
  );
}

export function WorkflowCard({
  workflow,
  snapshot,
  isOutlook,
  loading,
  onCreateReview,
  onOpenReview,
  onCreateDraftMail,
  onResetWorkflow,
  onReloadMail,
}: WorkflowCardProps) {
  const state = deriveState(workflow);

  const subject =
    workflow?.subject || snapshot?.subject || "Keine Mail geladen";

  const sender = workflow?.sender || snapshot?.from || "";

  if (!isOutlook && !snapshot) {
    return (
      <section className="card">
        <div className="empty-state">
          <ClockIcon size={20} />
          <div>
            Add-in wartet auf Outlook.
            <br />
            Bitte über das Mail-Ribbon starten.
          </div>
        </div>
      </section>
    );
  }

  const cardCls =
    state === "quote_sent"
      ? "card card-success"
      : state === "review_running" ||
          state === "review_created" ||
          state === "review_opened"
        ? "card card-info"
        : "card";

  return (
    <section className={cardCls}>
      <div className="card-stack">
        <div className="row-between">
          <StatusPill state={state} />

          {workflow?.review?.review_id && (
            <code className="review-id" title="Review-ID">
              {workflow.review.review_id}
            </code>
          )}
        </div>

        <div className="mail-subject">{subject}</div>

        {sender && <div className="mail-sender">{sender}</div>}

        {(state === "review_running" ||
          state === "review_created" ||
          state === "review_opened" ||
          state === "quote_sent") && (
          <div className="meta-grid">
            {workflow?.reviewCreatedAt && (
              <div className="meta-cell">
                <span className="meta-label">Review gestartet</span>
                <span className="meta-value">
                  {formatDate(workflow.reviewCreatedAt)}
                </span>
              </div>
            )}

            {workflow?.quoteSentAt && (
              <div className="meta-cell">
                <span className="meta-label">Versendet</span>
                <span className="meta-value">
                  {formatDate(workflow.quoteSentAt)}
                </span>
              </div>
            )}
          </div>
        )}

        <div className="actions">
          {state === "new" && (
            <>
              <button
                className="btn btn-primary"
                disabled={!isOutlook || loading || !snapshot}
                onClick={onCreateReview}
              >
                <SparkIcon className="btn-icon" />
                Review erstellen
              </button>

              <button
                className="btn btn-ghost"
                disabled={!isOutlook || loading}
                onClick={onReloadMail}
              >
                <RefreshIcon className="btn-icon" />
                Mail neu laden
              </button>
            </>
          )}

          {state === "review_running" && (
            <>
              <button
                className="btn btn-secondary"
                disabled={loading}
                onClick={onOpenReview}
              >
                <ExternalIcon className="btn-icon" />
                Statusseite öffnen
              </button>

              <button
                className="btn btn-ghost"
                disabled={loading}
                onClick={onResetWorkflow}
              >
                <TrashIcon className="btn-icon" />
                Aus Ansicht entfernen
              </button>
            </>
          )}

          {state === "review_created" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onOpenReview}
              >
                <ExternalIcon className="btn-icon" />
                Review-UI öffnen
              </button>

              <button
                className="btn btn-ghost"
                disabled={loading}
                onClick={onResetWorkflow}
              >
                <TrashIcon className="btn-icon" />
                Verwerfen & neu
              </button>
            </>
          )}

          {state === "review_opened" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onCreateDraftMail}
              >
                <SendIcon className="btn-icon" />
                Angebotsmail erstellen
              </button>

              <button
                className="btn btn-secondary"
                disabled={loading}
                onClick={onOpenReview}
              >
                <ExternalIcon className="btn-icon" />
                Review nochmal öffnen
              </button>
            </>
          )}

          {state === "quote_sent" && (
            <>
              <button
                className="btn btn-secondary"
                disabled={loading}
                onClick={onCreateDraftMail}
              >
                <SendIcon className="btn-icon" />
                Erneut versenden
              </button>

              <button
                className="btn btn-ghost"
                disabled={loading}
                onClick={onOpenReview}
              >
                <ExternalIcon className="btn-icon" />
                Review öffnen
              </button>

              <button
                className="btn btn-danger-ghost"
                disabled={loading}
                onClick={onResetWorkflow}
              >
                <TrashIcon className="btn-icon" />
                Workflow zurücksetzen
              </button>
            </>
          )}
        </div>

        {state === "quote_sent" && (
          <div className="success-banner">
            <CheckIcon className="btn-icon" />
            <span>Angebotsmail wurde erstellt.</span>
          </div>
        )}
      </div>
    </section>
  );
}