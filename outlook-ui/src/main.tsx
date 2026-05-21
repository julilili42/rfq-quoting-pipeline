/**
 * Outlook taskpane entry point.
 *
 * Layout (single column, top-down):
 *
 *   Steps indicator
 *   WorkflowCard          ← single source of truth (state + progress in one)
 *   StatusCard            ← only shown for active loading/error feedback
 *   Quoting-Übersicht link ← prominent, with arrow
 *
 * State source of truth
 * ---------------------
 * All workflow state is server-authoritative. The Outlook itemId is sent
 * with the create-review request and persisted on the review row.
 * Subsequent loads call `/api/reviews/by-outlook-item/{id}` to recover
 * the bound review's state (approval state, pipeline progress, opened/
 * approved/sent timestamps). The high-level `MailWorkflowState` is
 * derived from those server signals — there is no localStorage cache.
 */

import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import {
  detachOutlookItem,
  getMailSettings,
  getOutlookItemStatus,
  markReviewOpened,
  pollReviewUntilComplete,
  ReviewNotFoundError,
  startReview,
  transitionApprovalToReadyToSend,
} from "./api/reviewApi";
import {
  BatchWorkflowCard,
  type BatchDraftItem,
} from "./components/BatchWorkflowCard";
import { ExternalIcon } from "./components/Icons";
import { StatusCard } from "./components/StatusCard";
import { Steps } from "./components/Steps";
import { WorkflowCard } from "./components/WorkflowCard";
import { createDraftMail, openUrl } from "./outlook/draftMail";
import {
  getSelectedMailItems,
  readMailSnapshot,
  readSelectedMailSnapshot,
  type SelectedMailSummary,
} from "./outlook/mailbox";
import {
  type MailWorkflow,
  type MailWorkflowState,
  type OutlookItemStatus,
  buildWorkflowFromStatus,
  deriveMailId,
} from "./serverWorkflow";
import type {
  CreateReviewResponse,
  MailSnapshot,
  PipelineProgress,
} from "./types";
import { REVIEW_API_URL, REVIEW_UI_URL } from "./config";

import "./style.css";

declare const Office: any;

const REVIEW_OVERVIEW_URL = REVIEW_UI_URL;
// Workflow states where polling the by-outlook-item endpoint is meaningful.
const STATES_TO_POLL_STATUS: MailWorkflowState[] = [
  "review_created",
  "review_opened",
];

const STATUS_POLL_INTERVAL_MS = 4000;


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

function formatSelectionStatus(items: SelectedMailSummary[]): string {
  const label = items.some((item) => item.collapsedCount > 1)
    ? "Unterhaltungen"
    : "Mails";
  return `${items.length} ${label} ausgewählt.`;
}

function shouldShowStatusCard(
  status: string,
  loading: boolean,
  pipelineVisible: boolean,
  pipelineFailed: boolean,
): boolean {
  // Pipeline failures already render inline inside the WorkflowCard
  // (step name + error message), so a second copy down here is noise.
  if (pipelineFailed) return false;
  if (loading && !pipelineVisible) return true;
  return (
    status.startsWith("Fehler") ||
    status.includes("fehlgeschlagen") ||
    status.includes("konnte nicht")
  );
}

function isCompletedBatch(items: BatchDraftItem[]): boolean {
  return (
    items.length > 0 &&
    items.every((item) => item.status === "completed")
  );
}

function OverviewLink() {
  return (
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
  );
}

function App() {
  const [isOutlook, setIsOutlook] = useState(false);
  const [mailId, setMailId] = useState<string | null>(null);
  const [selectedItems, setSelectedItems] = useState<SelectedMailSummary[]>([]);
  const [batchItems, setBatchItems] = useState<BatchDraftItem[]>([]);
  const [snapshot, setSnapshot] = useState<MailSnapshot | null>(null);
  const [workflow, setWorkflow] = useState<MailWorkflow | null>(null);
  const [pipelineProgress, setPipelineProgress] =
    useState<PipelineProgress | null>(null);
  const [status, setStatus] = useState("Bereit. Add-in wartet auf Outlook.");
  const [loading, setLoading] = useState(false);

  const pollingReviewIdRef = useRef<string | null>(null);
  const statusPollTimerRef = useRef<number | null>(null);

  /**
   * Fetch the bound review's status from the server and build a
   * MailWorkflow view-model. Returns null when no review is bound.
   */
  async function loadServerWorkflow(
    targetMailId: string,
  ): Promise<{ workflow: MailWorkflow | null; status: OutlookItemStatus | null }> {
    try {
      const remote = await getOutlookItemStatus(targetMailId);
      return {
        workflow: buildWorkflowFromStatus(targetMailId, remote),
        status: remote,
      };
    } catch (error) {
      if (error instanceof ReviewNotFoundError) {
        return { workflow: null, status: null };
      }
      throw error;
    }
  }

  async function refreshServerWorkflow(targetMailId: string): Promise<MailWorkflow | null> {
    try {
      const { workflow: wf } = await loadServerWorkflow(targetMailId);
      setWorkflow(wf);
      return wf;
    } catch (error) {
      setStatus(`Fehler beim Laden des Workflows: ${String(error)}`);
      return workflow;
    }
  }

  async function loadMail() {
    setLoading(true);
    setStatus("Lade Outlook-Auswahl…");
    try {
      const currentItem = Office.context?.mailbox?.item;
      setBatchItems([]);

      if (currentItem) {
        setSelectedItems([]);
        setStatus("Lade Mail-Inhalt und Anhänge…");
        const mail = await readMailSnapshot();
        const id = deriveMailId(currentItem, mail);
        const { workflow: existingWorkflow } = await loadServerWorkflow(id);
        setMailId(id);
        setSnapshot(mail);
        setWorkflow(existingWorkflow);
        setStatus(
          `Mail geladen — ${mail.attachments.length} ${
            mail.attachments.length === 1 ? "Anhang" : "Anhänge"
          }.`,
        );
        return;
      }

      const selected = await getSelectedMailItems();
      setSelectedItems(selected);

      if (selected.length > 1) {
        setMailId(null);
        setSnapshot(null);
        setWorkflow(null);
        setPipelineProgress(null);
        setStatus(formatSelectionStatus(selected));
        return;
      }

      if (selected.length === 0) {
        setMailId(null);
        setSnapshot(null);
        setWorkflow(null);
        setPipelineProgress(null);
        setStatus("Keine Mail ausgewählt.");
        return;
      }

      setStatus("Lade Mail-Inhalt und Anhänge…");
      const mail = await readSelectedMailSnapshot(selected[0].itemId);
      const id = deriveMailId({ itemId: selected[0].itemId }, mail);
      const { workflow: existingWorkflow } = await loadServerWorkflow(id);
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

  function patchBatchItem(
    itemId: string,
    patch: Partial<BatchDraftItem>,
  ) {
    setBatchItems((items) =>
      items.map((item) =>
        item.itemId === itemId ? { ...item, ...patch } : item,
      ),
    );
  }

  async function handleCreateBatchReviews() {
    if (selectedItems.length === 0) return;

    setLoading(true);
    setPipelineProgress(null);
    setBatchItems(
      selectedItems.map((item) => ({ ...item, status: "pending" })),
    );
    setStatus("Batch gestartet.");

    let completedCount = 0;
    let failedCount = 0;

    const jobs: Array<{
      selected: SelectedMailSummary;
      mail: MailSnapshot;
      itemMailId: string;
    }> = [];

    for (const selected of selectedItems) {
      patchBatchItem(selected.itemId, {
        status: "loading",
        detail: "Mail-Inhalt und Anhänge werden geladen…",
      });

      try {
        const mail = await readSelectedMailSnapshot(selected.itemId);
        const itemMailId = deriveMailId({ itemId: selected.itemId }, mail);
        jobs.push({ selected, mail, itemMailId });
        patchBatchItem(selected.itemId, {
          status: "pending",
          detail: "Bereit für Pipeline",
        });
      } catch (error) {
        failedCount += 1;
        patchBatchItem(selected.itemId, {
          status: "failed",
          error: String(error),
        });
      }
    }

    if (jobs.length === 0) {
      setStatus(`${failedCount} Mails konnten nicht geladen werden.`);
      setLoading(false);
      return;
    }

    setStatus("Pipelines werden gestartet…");

    async function processOne({
      selected,
      mail,
      itemMailId,
    }: {
      selected: SelectedMailSummary;
      mail: MailSnapshot;
      itemMailId: string;
    }) {
      patchBatchItem(selected.itemId, {
        status: "running",
        detail: "Pipeline wird gestartet…",
      });

      try {
        const started = await startReview(mail, itemMailId);
        patchBatchItem(selected.itemId, {
          status: "running",
          reviewId: started.review_id,
          detail: "Pipeline läuft…",
        });

        const completed = await pollReviewUntilComplete(
          started,
          (progress) => {
            patchBatchItem(selected.itemId, {
              status: "running",
              detail: formatProgressStatus(progress),
            });
          },
        );

        completedCount += 1;
        patchBatchItem(selected.itemId, {
          status: "completed",
          reviewId: completed.review_id,
          detail: undefined,
        });
      } catch (error) {
        failedCount += 1;
        patchBatchItem(selected.itemId, {
          status: "failed",
          error: String(error),
        });
      }
    }

    const CONCURRENCY = 3;
    let cursor = 0;
    const workerCount = Math.min(CONCURRENCY, jobs.length);
    const workers = Array.from({ length: workerCount }, async () => {
      while (true) {
        const index = cursor++;
        if (index >= jobs.length) return;
        await processOne(jobs[index]);
      }
    });
    await Promise.all(workers);

    setStatus(
      failedCount > 0
        ? `${completedCount} Reviews erstellt, ${failedCount} fehlgeschlagen.`
        : `${completedCount} Reviews erstellt. Bereit zur Review-Inbox.`,
    );
    setLoading(false);
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
      const updated = await refreshServerWorkflow(targetMailId);
      setPipelineProgress(completed.progress ?? null);
      setStatus(`Review erstellt: ${completed.review_id}.`);
      if (openWhenReady && updated) {
        handleOpenReview(updated);
      }
    } finally {
      pollingReviewIdRef.current = null;
      setLoading(false);
    }
  }

  async function handleCreateReview(openWhenReady = false) {
    if (!mailId) return;
    setLoading(true);
    setPipelineProgress(null);
    setStatus("Review wird gestartet…");
    try {
      const mail = snapshot ?? (await readMailSnapshot());
      setSnapshot(mail);
      const started = await startReview(mail, mailId);
      // Refresh once now so the card flips to review_running immediately;
      // pipeline polling below will pull in the completed state later.
      await refreshServerWorkflow(mailId);
      setStatus(`Pipeline gestartet: ${started.review_id}.`);
      await awaitReviewCompletion(started, mailId, openWhenReady);
    } catch (error) {
      setStatus(`Fehler beim Erstellen des Reviews: ${String(error)}`);
      setLoading(false);
    }
  }

  async function handleOpenReview(wf: MailWorkflow | null = workflow) {
    if (!wf?.reviewId || !mailId) {
      setStatus("Kein Review zur Mail vorhanden.");
      return;
    }
    openUrl(reviewUiUrl(wf.reviewId));

    // Record the first open server-side so cross-device reloads agree.
    if (!wf.reviewOpenedAt) {
      try {
        await markReviewOpened(wf.reviewId);
        await refreshServerWorkflow(mailId);
      } catch (error) {
        // Non-fatal: the URL was opened, just the timestamp didn't stick.
        // Next status poll will pick it up if the request actually landed.
        console.warn("mark-opened failed:", error);
      }
    }
    setStatus(`Review-UI geöffnet (${wf.reviewId}).`);
  }

  async function handleCreateDraftMail() {
    if (!workflow?.reviewId || !mailId) {
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
    const reviewId = workflow.reviewId;
    try {
      const { kundenFirma, recipientEmail, templates } = await getMailSettings(reviewId).catch(
        () => ({ kundenFirma: null, recipientEmail: null, templates: undefined }),
      );
      await createDraftMail(
        {
          review_id: reviewId,
          review_url: workflow.reviewUrl ?? reviewUiUrl(reviewId),
          draft_pdf_url: `${REVIEW_API_URL}/${reviewId}/pdf/draft`,
          draft_pdf_filename: workflow.finalPdfFilename ?? "",
          final_pdf_url: `${REVIEW_API_URL}/${reviewId}/pdf/final`,
          final_pdf_filename: workflow.finalPdfFilename,
        },
        {
          subject: workflow.subject || snapshot?.subject || "",
          kundenFirma: workflow.kundenFirma ?? kundenFirma ?? undefined,
          recipientEmail: recipientEmail ?? undefined,
          overrideFilename: workflow.finalPdfFilename,
        },
        setStatus,
        templates,
      );
      // Draft mail open in Outlook → flip backend to ready_to_send. We
      // don't roll back if this fails — the user already sees the draft.
      try {
        await transitionApprovalToReadyToSend(reviewId);
      } catch (error) {
        console.warn("ready_to_send transition failed:", error);
      }
      await refreshServerWorkflow(mailId);
    } catch (error) {
      setStatus(`Fehler beim Öffnen der Mail: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleResetWorkflow() {
    if (!mailId) return;
    setLoading(true);
    try {
      await detachOutlookItem(mailId);
      setWorkflow(null);
      setPipelineProgress(null);
      setStatus("Workflow zurückgesetzt. Neue Anfrage bereit.");
    } catch (error) {
      setStatus(`Fehler beim Zurücksetzen: ${String(error)}`);
    } finally {
      setLoading(false);
    }
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
      void loadMail();
      const itemChanged = Office.EventType?.ItemChanged;
      if (itemChanged) {
        Office.context?.mailbox?.addHandlerAsync?.(
          itemChanged,
          () => void loadMail(),
        );
      }
      const selectedItemsChanged = Office.EventType?.SelectedItemsChanged;
      if (selectedItemsChanged) {
        Office.context?.mailbox?.addHandlerAsync?.(
          selectedItemsChanged,
          () => void loadMail(),
        );
      }
    });
  }, []);

  // Refresh when the user returns from the Review-UI to Outlook. Office/webview
  // hosts may throttle intervals while the taskpane is in the background.
  useEffect(() => {
    if (!isOutlook) return;

    let lastRefreshAt = 0;
    function refreshOnReturn() {
      const now = Date.now();
      if (now - lastRefreshAt < 500) return;
      lastRefreshAt = now;

      if (mailId && workflow?.reviewId) {
        void refreshServerWorkflow(mailId);
        return;
      }
      void loadMail();
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        refreshOnReturn();
      }
    }

    window.addEventListener("focus", refreshOnReturn);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("focus", refreshOnReturn);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOutlook, mailId, workflow?.reviewId]);

  // ------------------------------------------------------------------
  // Resume pipeline polling on reload while pipeline is still running.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!mailId) return;
    if (!workflow?.reviewId) return;
    if (workflow.state !== "review_running") return;

    const currentMailId = mailId;
    const currentReviewId = workflow.reviewId;
    if (pollingReviewIdRef.current === currentReviewId) {
      return;
    }

    let cancelled = false;
    async function resumePolling() {
      try {
        setStatus(`Pipeline-Status wird fortgesetzt (${currentReviewId})…`);
        // Build a minimal CreateReviewResponse for the existing poller.
        await awaitReviewCompletion(
          {
            review_id: currentReviewId,
            review_url: "",
            draft_pdf_url: "",
            draft_pdf_filename: "",
          },
          currentMailId,
          false,
        );
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ReviewNotFoundError) {
          setWorkflow(null);
          setPipelineProgress(null);
          setStatus(
            "Vorheriger Review existiert nicht mehr — Workflow zurückgesetzt.",
          );
          return;
        }
        setStatus(
          `Pipeline konnte nicht abgeschlossen werden: ${String(error)}`,
        );
      }
    }
    void resumePolling();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mailId, workflow?.state, workflow?.reviewId]);

  // ------------------------------------------------------------------
  // Status polling. While the user is reviewing/approving server-side,
  // poll the by-outlook-item endpoint so the card moves into `approved`
  // (or `quote_sent` if approval was given on another device).
  // ------------------------------------------------------------------
  useEffect(() => {
    if (statusPollTimerRef.current !== null) {
      window.clearInterval(statusPollTimerRef.current);
      statusPollTimerRef.current = null;
    }

    if (!mailId || !workflow?.reviewId) return;
    if (!STATES_TO_POLL_STATUS.includes(workflow.state)) return;

    let cancelled = false;
    const currentMailId = mailId;

    async function checkOnce() {
      if (cancelled) return;
      try {
        const next = await getOutlookItemStatus(currentMailId);
        if (cancelled) return;
        const updated = buildWorkflowFromStatus(currentMailId, next);
        setWorkflow(updated);
      } catch (error) {
        if (error instanceof ReviewNotFoundError) {
          if (cancelled) return;
          setWorkflow(null);
          setPipelineProgress(null);
          setStatus(
            "Vorheriger Review existiert nicht mehr — Workflow zurückgesetzt.",
          );
          if (statusPollTimerRef.current !== null) {
            window.clearInterval(statusPollTimerRef.current);
            statusPollTimerRef.current = null;
          }
          return;
        }
        /* Other endpoint failures are non-fatal — keep polling. */
      }
    }

    void checkOnce();
    statusPollTimerRef.current = window.setInterval(
      checkOnce,
      STATUS_POLL_INTERVAL_MS,
    );

    return () => {
      cancelled = true;
      if (statusPollTimerRef.current !== null) {
        window.clearInterval(statusPollTimerRef.current);
        statusPollTimerRef.current = null;
      }
    };
  }, [mailId, workflow?.state, workflow?.reviewId]);

  // ------------------------------------------------------------------
  // Render.
  // ------------------------------------------------------------------
  const workflowState = workflow?.state ?? "new";
  const pipelineVisible =
    workflowState === "review_running" &&
    (loading || (pipelineProgress !== null && pipelineProgress.status !== "completed"));
  const pipelineFailed =
    pipelineProgress?.status === "failed" ||
    !!pipelineProgress?.steps?.some((s) => s.status === "failed");
  const showStatusCard = shouldShowStatusCard(
    status,
    loading,
    pipelineVisible,
    pipelineFailed,
  );
  const batchCompleted = isCompletedBatch(batchItems);
  const batchStarted = batchItems.length > 0;
  const batchWorkflowState: MailWorkflowState = batchCompleted
    ? "review_created"
    : batchStarted
      ? "review_running"
      : "new";

  if (selectedItems.length > 1) {
    return (
      <div className="panel">
        <Steps workflowState={batchWorkflowState} />

        <BatchWorkflowCard
          selectedItems={selectedItems}
          batchItems={batchItems}
          loading={loading}
          onCreateBatch={handleCreateBatchReviews}
          onReloadSelection={loadMail}
          onOpenOverview={() => openUrl(REVIEW_OVERVIEW_URL)}
        />
        {shouldShowStatusCard(status, false, false, false) && (
          <StatusCard status={status} loading={loading} />
        )}
        {!batchCompleted && <OverviewLink />}
      </div>
    );
  }

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

      <OverviewLink />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
