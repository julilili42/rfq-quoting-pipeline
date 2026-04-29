/**
 * WorkflowCard — the single source of truth for the current mail's state.
 *
 * Design intent
 * -------------
 * One card. Always. Whatever the current state — new, pipeline running,
 * review ready, sent — the user sees a single card with the relevant
 * action front and centre. Pipeline progress no longer lives in a
 * separate box; it folds into this card with a slim progress bar and a
 * collapsible step list for users who want the detail.
 */
import type { MailSnapshot, PipelineProgress } from "../types";
import type {
  MailWorkflow,
  MailWorkflowState,
} from "../mailWorkflowStorage";

import {
  AlertIcon,
  CheckIcon,
  ChevronDown,
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
  pipelineProgress: PipelineProgress | null;
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
    new: { label: "Neue Anfrage", cls: "pill pill-neutral" },
    review_running: { label: "Pipeline läuft", cls: "pill pill-info" },
    review_created: { label: "Review bereit", cls: "pill pill-info" },
    review_opened: { label: "In Bearbeitung", cls: "pill pill-info" },
    quote_sent: { label: "Angebot versendet", cls: "pill pill-success" },
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
  pipelineProgress,
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

  const showProgress =
    state === "review_running" && pipelineProgress &&
    pipelineProgress.status !== "completed";

  const failed =
    pipelineProgress?.status === "failed" ||
    pipelineProgress?.steps?.some((s) => s.status === "failed");

  return (
    <section className={`${cardCls} ${failed ? "card-error" : ""}`}>
      <div className="card-stack">
        <div className="row-between">
          <StatusPill state={state} />
          {workflow?.review?.review_id && (
            <code className="review-id" title="Review-ID">
              {workflow.review.review_id}
            </code>
          )}
        </div>

        <div>
          <div className="mail-subject">{subject}</div>
          {sender && <div className="mail-sender">{sender}</div>}
        </div>

        {showProgress && pipelineProgress && (
          <PipelineInline progress={pipelineProgress} />
        )}

        {(state === "review_created" ||
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
                Draft erstellen
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
            <button
              className="btn btn-ghost"
              disabled={loading}
              onClick={onResetWorkflow}
            >
              <TrashIcon className="btn-icon" />
              Aus Ansicht entfernen
            </button>
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

/* ------------------------------------------------------------------
 * Inline pipeline progress, folded into the workflow card.
 * ------------------------------------------------------------------ */

function PipelineInline({ progress }: { progress: PipelineProgress }) {
  const failed = progress.status === "failed";
  const steps = Array.isArray(progress.steps) ? progress.steps : [];
  const percent =
    typeof progress.progress_percent === "number"
      ? Math.max(0, Math.min(100, progress.progress_percent))
      : 0;

  return (
    <div className="pipeline-inline">
      <div className="pipeline-inline-current">
        <span
          className={
            failed ? "pipeline-inline-icon-error" : "pipeline-inline-icon-running"
          }
        >
          {failed ? <AlertIcon size={14} /> : <RefreshIcon size={14} />}
        </span>
        <span className="pipeline-inline-text">
          {progress.current_step || "Pipeline"}
          {progress.current_detail ? ` — ${progress.current_detail}` : ""}
        </span>
      </div>

      <div
        className="pipeline-progress-bar"
        aria-label={`Pipeline-Fortschritt ${percent}%`}
      >
        <div
          className="pipeline-progress-fill"
          style={{ width: `${percent}%` }}
        />
      </div>

      {steps.length > 0 && (
        <details className="pipeline-inline-details">
          <summary>
            <ChevronDown size={12} />
            <span>Schritte anzeigen</span>
            <span className="advanced-meta">
              {steps.filter((s) => s.status === "completed").length}/
              {steps.length}
            </span>
          </summary>
          <div className="pipeline-steps">
            {steps.map((step, index) => (
              <div
                key={`${step.name}-${index}`}
                className={`pipeline-step pipeline-step-${step.status}`}
              >
                <div className="pipeline-step-body">
                  <div className="pipeline-step-name">
                    {step.name || "Schritt"}
                  </div>
                  {step.detail && (
                    <div className="pipeline-step-detail">{step.detail}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {progress.error && (
        <div className="pipeline-error">{progress.error}</div>
      )}
    </div>
  );
}
