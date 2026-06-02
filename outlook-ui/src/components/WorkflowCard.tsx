/**
 * WorkflowCard — the single source of truth for the current mail's state.
 *
 * Approval gating
 * ---------------
 * The "Angebotsmail erstellen" button now requires explicit approval.
 * It only enables in the `approved` workflow state, which is reached
 * after the user clicks "Freigeben" inside the Review-UI and the plugin
 * has polled the API once. In `review_opened` the primary action sends
 * the user back to the Review-UI so the required next step is clear.
 *
 * Visual states map onto the 3-step stepper as:
 *   new            → step 01 Anfrage
 *   review_running → step 02 Pipeline
 *   review_created
 *   review_opened
 *   approved
 *   quote_sent     → step 03 Review (quote_sent shows a "done" check)
 */

import type { MailSnapshot, PipelineProgress } from "../types";
import type {
  MailWorkflow,
  MailWorkflowState,
} from "../serverWorkflow";

import {
  AlertIcon,
  CheckIcon,
  ClockIcon,
  ExternalIcon,
  RefreshIcon,
  SendIcon,
  StopIcon,
  TrashIcon,
} from "./Icons";
import { SecondaryActions } from "./ActionHelpers";

type WorkflowCardProps = {
  workflow: MailWorkflow | null;
  snapshot: MailSnapshot | null;
  isOutlook: boolean;
  loading: boolean;
  pipelineProgress: PipelineProgress | null;
  onCreateReview: (openWhenReady?: boolean) => void;
  onOpenReview: () => void;
  onCreateDraftMail: () => void;
  onResetWorkflow: () => void;
  onStopPipeline: () => void;
  onReloadMail: () => void;
  onOpenOverview: () => void;
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

function formatRetryDelay(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "sofort";
  if (seconds < 10) return `${seconds.toFixed(1).replace(".0", "")}s`;
  return `${Math.round(seconds)}s`;
}

function parseSender(sender: string): { name: string; email?: string } {
  const match = sender.match(/^\s*(.*?)\s*<([^<>]+)>\s*$/);
  if (!match) return { name: sender };
  return {
    name: match[1].trim() || match[2].trim(),
    email: match[2].trim(),
  };
}

function deriveState(workflow: MailWorkflow | null): MailWorkflowState {
  return workflow?.state ?? "new";
}

function StatusPill({ state }: { state: MailWorkflowState }) {
  const meta: Record<MailWorkflowState, { label: string; cls: string }> = {
    new:             { label: "Neue Anfrage",       cls: "pill pill-neutral" },
    review_running:  { label: "Pipeline läuft",     cls: "pill pill-info" },
    review_created:  { label: "Review bereit",      cls: "pill pill-info" },
    review_opened:   { label: "Wartet auf Freigabe", cls: "pill pill-warning" },
    approved:        { label: "Freigegeben",        cls: "pill pill-success" },
    quote_sent:      { label: "Angebot versendet",  cls: "pill pill-success" },
  };
  const { label, cls } = meta[state];
  return (
    <span className={cls}>
      <span className="pill-dot" />
      {label}
    </span>
  );
}

function OverviewAction({
  disabled,
  onOpenOverview,
}: {
  disabled: boolean;
  onOpenOverview: () => void;
}) {
  return (
    <button
      className="btn btn-ghost"
      disabled={disabled}
      onClick={onOpenOverview}
    >
      <ExternalIcon className="btn-icon" />
      Quoting-Übersicht öffnen
    </button>
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
  onStopPipeline,
  onReloadMail,
  onOpenOverview,
}: WorkflowCardProps) {
  const state = deriveState(workflow);
  const stopped = pipelineProgress?.status === "cancelled";
  // Stop is only meaningful while the run is genuinely in flight.
  const canStop =
    state === "review_running" &&
    pipelineProgress?.status !== "failed" &&
    pipelineProgress?.status !== "cancelled";
  const subject =
    workflow?.subject || snapshot?.subject || "Keine Mail geladen";
  const sender = workflow?.sender || snapshot?.from || "";
  const parsedSender = sender ? parseSender(sender) : null;

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
    state === "quote_sent" || state === "approved"
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
          <div className="row-inline">
            {stopped ? (
              <span className="pill pill-warning">
                <span className="pill-dot" />
                Gestoppt
              </span>
            ) : (
              <StatusPill state={state} />
            )}
          </div>
          {state === "new" && (
            <button
              type="button"
              className="icon-button"
              disabled={loading}
              onClick={onReloadMail}
              aria-label="Mail neu laden"
              title="Mail neu laden"
            >
              <RefreshIcon className="icon-button-icon" />
            </button>
          )}
        </div>

        <div>
          <div className="mail-subject">{subject}</div>
          {parsedSender && (
            <div className="mail-sender">
              <span className="mail-sender-name">{parsedSender.name}</span>
              {parsedSender.email && (
                <span className="mail-sender-email">{parsedSender.email}</span>
              )}
            </div>
          )}
        </div>

        {showProgress && pipelineProgress && (
          <PipelineInline progress={pipelineProgress} />
        )}

        {(state === "review_created" ||
          state === "review_opened" ||
          state === "approved" ||
          state === "quote_sent") && (
          <div className="meta-strip">
            {workflow?.reviewCreatedAt && (
              <span className="meta-chip">
                <ClockIcon size={12} />
                <span className="meta-chip-label">Start</span>
                <span className="meta-value">
                  {formatDate(workflow.reviewCreatedAt)}
                </span>
              </span>
            )}
            {workflow?.approvedAt && (
              <span className="meta-chip">
                <CheckIcon size={12} />
                <span className="meta-chip-label">Freigabe</span>
                <span className="meta-value">
                  {formatDate(workflow.approvedAt)}
                </span>
              </span>
            )}
            {workflow?.quoteSentAt && (
              <span className="meta-chip">
                <SendIcon size={12} />
                <span className="meta-chip-label">Mail</span>
                <span className="meta-value">
                  {formatDate(workflow.quoteSentAt)}
                </span>
              </span>
            )}
          </div>
        )}

        <div className="actions">
          {state === "new" && (
            <>
              <button
                className="btn btn-primary"
                disabled={!isOutlook || loading || !snapshot}
                onClick={() => onCreateReview(true)}
              >
                Review starten
              </button>
              <SecondaryActions>
                <OverviewAction
                  disabled={loading}
                  onOpenOverview={onOpenOverview}
                />
              </SecondaryActions>
            </>
          )}

          {state === "review_running" && (
            <SecondaryActions>
              {canStop && (
                <button
                  className="btn btn-danger-ghost"
                  disabled={!workflow?.reviewId}
                  onClick={onStopPipeline}
                >
                  <StopIcon className="btn-icon" />
                  Pipeline stoppen
                </button>
              )}
              <button
                className="btn btn-ghost"
                onClick={onResetWorkflow}
              >
                <RefreshIcon className="btn-icon" />
                Neu starten
              </button>
              <OverviewAction
                disabled={false}
                onOpenOverview={onOpenOverview}
              />
            </SecondaryActions>
          )}

          {state === "review_created" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onOpenReview}
              >
                <ExternalIcon className="btn-icon" />
                Review öffnen
              </button>
              <SecondaryActions>
                <OverviewAction
                  disabled={loading}
                  onOpenOverview={onOpenOverview}
                />
                <button
                  className="btn btn-ghost"
                  disabled={loading}
                  onClick={onResetWorkflow}
                >
                  <TrashIcon className="btn-icon" />
                  Neu starten
                </button>
              </SecondaryActions>
            </>
          )}

          {state === "review_opened" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onOpenReview}
              >
                Review öffnen
              </button>
              <SecondaryActions>
                <OverviewAction
                  disabled={loading}
                  onOpenOverview={onOpenOverview}
                />
              </SecondaryActions>
            </>
          )}

          {state === "approved" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onCreateDraftMail}
              >
                <SendIcon className="btn-icon" />
                Angebotsmail erstellen
              </button>
              <SecondaryActions>
                <button
                  className="btn btn-ghost"
                  disabled={loading}
                  onClick={onOpenReview}
                >
                  <ExternalIcon className="btn-icon" />
                  Review öffnen
                </button>
                <OverviewAction
                  disabled={loading}
                  onOpenOverview={onOpenOverview}
                />
              </SecondaryActions>
            </>
          )}

          {state === "quote_sent" && (
            <>
              <button
                className="btn btn-primary"
                disabled={loading}
                onClick={onCreateDraftMail}
              >
                <SendIcon className="btn-icon" />
                Mail erneut erstellen
              </button>
              <SecondaryActions>
                <button
                  className="btn btn-ghost"
                  disabled={loading}
                  onClick={onOpenReview}
                >
                  <ExternalIcon className="btn-icon" />
                  Review öffnen
                </button>
                <OverviewAction
                  disabled={loading}
                  onOpenOverview={onOpenOverview}
                />
                <button
                  className="btn btn-danger-ghost"
                  disabled={loading}
                  onClick={onResetWorkflow}
                >
                  <TrashIcon className="btn-icon" />
                  Neu starten
                </button>
              </SecondaryActions>
            </>
          )}
        </div>

      </div>
    </section>
  );
}

/* ------------------------------------------------------------------
 * Inline pipeline progress, folded into the workflow card.
 * ------------------------------------------------------------------ */

function PipelineInline({ progress }: { progress: PipelineProgress }) {
  const failed = progress.status === "failed";
  const cancelled = progress.status === "cancelled";
  const terminal = failed || cancelled;
  const retry = progress.llm_retry;
  const percent =
    typeof progress.progress_percent === "number"
      ? Math.max(0, Math.min(100, progress.progress_percent))
      : 0;

  return (
    <div className="pipeline-inline">
      <div className="pipeline-inline-current">
        <span
          className={
            terminal ? "pipeline-inline-icon-error" : "pipeline-inline-icon-running"
          }
        >
          {failed ? (
            <AlertIcon size={14} />
          ) : cancelled ? (
            <StopIcon size={14} />
          ) : (
            <RefreshIcon size={14} />
          )}
        </span>
        <span className="pipeline-inline-text">
          {retry
            ? `Retry ${retry.next_attempt}/${retry.max_attempts} in ${formatRetryDelay(
                retry.delay_s,
              )}`
            : `${progress.current_step || "Pipeline"}${
                progress.current_detail ? ` — ${progress.current_detail}` : ""
              }`}
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

    </div>
  );
}
