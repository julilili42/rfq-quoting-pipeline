/**
 * Outlook taskpane entry point.
 *
 * Layout (single column, top-down):
 *
 *   Steps indicator
 *   WorkflowCard          ← single source of truth (state + progress in one)
 *   StatusCard            ← only shown when workflow card doesn't cover it
 *                           (initial load, errors, mail-loading)
 *   Quoting-Übersicht link ← prominent, with arrow
 *
 * The StatusCard used to render under every state, which produced two
 * "Pipeline läuft" / "Extraktion" labels at once — once inside the
 * WorkflowCard, once below it. We now hide the StatusCard whenever
 * the WorkflowCard already names the state (review_running through
 * quote_sent) and only surface it for the truly informational stages:
 * initial load, errors, and the new state.
 *
 * Approval polling
 * ----------------
 * After the user opens the Review-UI we poll the backend's
 * `/api/reviews/{id}/approval` endpoint. Once the state flips to
 * `approved` (or `ready_to_send`) we move the workflow into the
 * `approved` state, which unlocks the "Angebotsmail erstellen"
 * button in the WorkflowCard.
 */

import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import {
  getApprovalState,
  getMailSettings,
  isApproved,
  pollReviewUntilComplete,
  startReview,
} from "./api/reviewApi";
import { ExternalIcon } from "./components/Icons";
import { StatusCard } from "./components/StatusCard";
import { Steps } from "./components/Steps";
import { WorkflowCard } from "./components/WorkflowCard";
import { createDraftMail, openUrl } from "./outlook/draftMail";
import { readMailSnapshot } from "./outlook/mailbox";
import {
  type MailWorkflow,
  type MailWorkflowState,
  deleteWorkflow,
  deriveMailId,
  getWorkflow,
  maybeMigrateLegacy,
  upsertWorkflow,
} from "./mailWorkflowStorage";
import type {
  CreateReviewResponse,
  MailSnapshot,
  PipelineProgress,
} from "./types";
import { REVIEW_UI_URL } from "./config";

import "./style.css";

declare const Office: any;

const REVIEW_OVERVIEW_URL = REVIEW_UI_URL;
// Workflow states whose UI is fully described by the WorkflowCard.
// During these states the StatusCard would just repeat what's already
// visible, so we hide it.
const STATES_WITH_OWN_STATUS: MailWorkflowState[] = [
  "review_running",
  "review_created",
  "review_opened",
  "approved",
  "quote_sent",
];

// Workflow states where polling the approval endpoint is meaningful.
const STATES_TO_POLL_APPROVAL: MailWorkflowState[] = [
  "review_created",
  "review_opened",
];

const APPROVAL_POLL_INTERVAL_MS = 4000;


function reviewUiUrl(reviewId: string): string {
  return `${REVIEW_UI_URL}/reviews/${reviewId}`;
}

function formatProgressStatus(progress: PipelineProgress): string {
  if (progress.status === "failed") {
    return `Pipeline-Fehler bei ${progress.current_step}: ${
      progress.error || "Unbekannter Fehler"
    }`;
  }
  if (progress.status === "completed") {
    return "Pipeline abgeschlossen. Review ist bereit.";
  }
  return `Pipeline läuft: ${progress.current_step}`;
}

function App() {
  const [isOutlook, setIsOutlook] = useState(false);
  const [mailId, setMailId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<MailSnapshot | null>(null);
  const [workflow, setWorkflow] = useState<MailWorkflow | null>(null);
  const [pipelineProgress, setPipelineProgress] =
    useState<PipelineProgress | null>(null);
  const [status, setStatus] = useState("Bereit. Add-in wartet auf Outlook.");
  const [loading, setLoading] = useState(false);

  const pollingReviewIdRef = useRef<string | null>(null);
  const approvalPollTimerRef = useRef<number | null>(null);

  async function loadMail() {
    setLoading(true);
    setStatus("Lade Mail-Inhalt und Anhänge…");
    try {
      const mail = await readMailSnapshot();
      const id = deriveMailId(Office.context?.mailbox?.item, mail);
      maybeMigrateLegacy(id);
      const existingWorkflow = getWorkflow(id);
      setMailId(id);
      setSnapshot(mail);
      setWorkflow(existingWorkflow);
      setStatus(
        `Mail geladen — ${mail.attachments.length} ${
          mail.attachments.length === 1 ? "Anhang" : "Anhänge"
        }.`,
      );
    } catch (error) {
      setStatus(`Fehler beim Laden der Mail: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function awaitReviewCompletion(
    startedReview: CreateReviewResponse,
    targetMailId: string,
    openWhenReady: boolean,
  ) {
    if (pollingReviewIdRef.current === startedReview.review_id) {
      return;
    }
    pollingReviewIdRef.current = startedReview.review_id;
    setLoading(true);
    try {
      const completed = await pollReviewUntilComplete(
        startedReview,
        (progress) => {
          setPipelineProgress(progress);
          setStatus(formatProgressStatus(progress));
        },
      );
      const updated = upsertWorkflow(targetMailId, {
        state: "review_created",
        review: completed,
      });
      setWorkflow(updated);
      setPipelineProgress(completed.progress ?? null);
      setStatus(`Review erstellt: ${completed.review_id}.`);
      if (openWhenReady) {
        handleOpenReview(updated);
      }
    } finally {
      pollingReviewIdRef.current = null;
      setLoading(false);
    }
  }

  async function handleCreateReview() {
    if (!mailId) return;
    setLoading(true);
    setPipelineProgress(null);
    setStatus("Review wird gestartet…");
    try {
      const mail = snapshot ?? (await readMailSnapshot());
      setSnapshot(mail);
      const started = await startReview(mail);
      const runningWorkflow = upsertWorkflow(mailId, {
        subject: mail.subject,
        sender: mail.from,
        state: "review_running",
        review: started,
        reviewCreatedAt: new Date().toISOString(),
      });
      setWorkflow(runningWorkflow);
      setStatus(`Pipeline gestartet: ${started.review_id}.`);
      await awaitReviewCompletion(started, mailId, true);
    } catch (error) {
      setStatus(`Fehler beim Erstellen des Reviews: ${String(error)}`);
      setLoading(false);
    }
  }

  function handleOpenReview(wf: MailWorkflow | null = workflow) {
    if (!wf?.review || !mailId) {
      setStatus("Kein Review zur Mail vorhanden.");
      return;
    }
    openUrl(reviewUiUrl(wf.review.review_id));

    // Once opened, transition forward but never backwards.
    const nextState: MailWorkflowState =
      wf.state === "review_created" ? "review_opened" : wf.state;

    const updated = upsertWorkflow(mailId, {
      state: nextState,
      reviewOpenedAt: wf.reviewOpenedAt ?? new Date().toISOString(),
    });
    setWorkflow(updated);
    setStatus(`Review-UI geöffnet (${wf.review.review_id}).`);
  }

  async function handleCreateDraftMail() {
    if (!workflow?.review || !mailId) {
      setStatus("Kein Review zur Mail vorhanden.");
      return;
    }
    if (workflow.state !== "approved" && workflow.state !== "quote_sent") {
      setStatus(
        "Bitte zuerst die Freigabe in der Review-UI erteilen.",
      );
      return;
    }
    setLoading(true);
    setStatus("Öffne Angebotsmail mit finaler PDF…");
    try {
      const { templates } = await getMailSettings(workflow.review.review_id).catch(
        () => ({ kundenFirma: null, templates: undefined }),
      );
      await createDraftMail(
        workflow.review,
        {
          subject: workflow.subject || snapshot?.subject || "",
          kundenFirma: workflow.kundenFirma,
          overrideFilename: workflow.finalPdfFilename,
        },
        setStatus,
        templates,
      );
      const updated = upsertWorkflow(mailId, {
        state: "quote_sent",
        quoteSentAt: new Date().toISOString(),
      });
      setWorkflow(updated);
    } catch (error) {
      setStatus(`Fehler beim Öffnen der Mail: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleResetWorkflow() {
    if (!mailId) return;
    deleteWorkflow(mailId);
    setWorkflow(null);
    setPipelineProgress(null);
    setStatus("Workflow zurückgesetzt. Neue Anfrage bereit.");
  }

  // ------------------------------------------------------------------
  // Office init.
  // ------------------------------------------------------------------
  useEffect(() => {
    Office.onReady((info: any) => {
      if (info.host !== Office.HostType.Outlook) {
        setIsOutlook(false);
        setStatus(
          `Nicht im Outlook-Host gestartet. info.host=${String(info.host)}`,
        );
        return;
      }
      setIsOutlook(true);
      loadMail();
    });
  }, []);

  // ------------------------------------------------------------------
  // Resume pipeline polling on reload while pipeline is still running.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!mailId) return;
    if (!workflow?.review) return;
    if (workflow.state !== "review_running") return;

    const currentMailId = mailId;
    const currentReview = workflow.review;
    if (pollingReviewIdRef.current === currentReview.review_id) {
      return;
    }

    let cancelled = false;
    async function resumePolling() {
      try {
        setStatus(
          `Pipeline-Status wird fortgesetzt (${currentReview.review_id})…`,
        );
        await awaitReviewCompletion(currentReview, currentMailId, false);
      } catch (error) {
        if (!cancelled) {
          setStatus(
            `Pipeline konnte nicht abgeschlossen werden: ${String(error)}`,
          );
        }
      }
    }
    void resumePolling();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mailId, workflow?.state, workflow?.review?.review_id]);

  // ------------------------------------------------------------------
  // Approval polling. Runs while we're in a state where the user might
  // be approving in the Streamlit UI; flips workflow into `approved`
  // once the backend confirms approval.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (approvalPollTimerRef.current !== null) {
      window.clearInterval(approvalPollTimerRef.current);
      approvalPollTimerRef.current = null;
    }

    if (!mailId || !workflow?.review?.review_id) return;
    if (!STATES_TO_POLL_APPROVAL.includes(workflow.state)) return;

    let cancelled = false;
    const reviewId = workflow.review.review_id;
    const currentMailId = mailId;

    async function checkOnce() {
      if (cancelled) return;
      try {
        const record = await getApprovalState(reviewId);
        if (cancelled) return;
        if (isApproved(record)) {
          let kundenFirma: string | undefined;
          try {
            const { kundenFirma: kf } = await getMailSettings(reviewId);
            kundenFirma = kf ?? undefined;
          } catch { /* non-fatal */ }

          const updated = upsertWorkflow(currentMailId, {
            state: "approved",
            approvedAt: record.approved_at ?? new Date().toISOString(),
            approvedBy: record.approved_by ?? undefined,
            finalPdfFilename: record.final_pdf_path ?? undefined,
            kundenFirma,
          });
          setWorkflow(updated);
          setStatus("Freigegeben. Angebotsmail bereit.");
        }
      } catch {
        /*
         * Approval endpoint failures are non-fatal — keep polling.
         * Errors only matter if the user is actively trying to
         * proceed, in which case the next manual action will surface
         * the issue.
         */
      }
    }

    // Fire once immediately so transitions feel snappy, then on interval.
    void checkOnce();
    approvalPollTimerRef.current = window.setInterval(
      checkOnce,
      APPROVAL_POLL_INTERVAL_MS,
    );

    return () => {
      cancelled = true;
      if (approvalPollTimerRef.current !== null) {
        window.clearInterval(approvalPollTimerRef.current);
        approvalPollTimerRef.current = null;
      }
    };
  }, [mailId, workflow?.state, workflow?.review?.review_id]);

  // ------------------------------------------------------------------
  // Render.
  // ------------------------------------------------------------------
  const workflowState = workflow?.state ?? "new";
  const pipelineVisible =
    workflowState === "review_running" &&
    (loading || (pipelineProgress !== null && pipelineProgress.status !== "completed"));
  const showStatusCard =
    !STATES_WITH_OWN_STATUS.includes(workflowState) ||
    (workflowState === "review_running" && !pipelineVisible);

  return (
    <div className="panel">
      <Steps workflowState={workflowState} />

      <WorkflowCard
        workflow={workflow}
        snapshot={snapshot}
        isOutlook={isOutlook}
        loading={loading}
        pipelineProgress={pipelineProgress}
        onCreateReview={handleCreateReview}
        onOpenReview={() => handleOpenReview()}
        onCreateDraftMail={handleCreateDraftMail}
        onResetWorkflow={handleResetWorkflow}
        onReloadMail={loadMail}
      />

      {showStatusCard && <StatusCard status={status} loading={loading} />}

      <button
        className="overview-link"
        onClick={() => openUrl(REVIEW_OVERVIEW_URL)}
        type="button"
      >
        <span className="overview-link-text">
          Quoting-Übersicht öffnen
        </span>
        <ExternalIcon className="overview-link-icon" />
      </button>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
