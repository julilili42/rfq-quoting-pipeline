/**
 * Outlook taskpane entry point.
 *
 * Layout (single column, top-down):
 *
 *   Steps indicator
 *   WorkflowCard          ← single source of truth (state + progress in one)
 *   StatusCard            ← only shown for active loading/error feedback
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
  cancelReview,
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

type BatchRunOutcome = "completed" | "failed" | "cancelled";


function reviewUiUrl(reviewId: string): string {
  return `${REVIEW_UI_URL}/reviews/${reviewId}`;
}

function formatProgressStatus(progress: PipelineProgress): string {
  if (progress.status === "failed") {
    return progress.error
      ? `Fehler: ${progress.error}`
      : "Pipeline fehlgeschlagen.";
  }
  if (progress.status === "cancelled") {
    return "Pipeline gestoppt.";
  }
  if (progress.status === "completed") {
    return "Review bereit.";
  }
  return progress.current_step
    ? `${progress.current_step} läuft.`
    : "Pipeline läuft.";
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

function App() {
  const [isOutlook, setIsOutlook] = useState(false);
  const [mailId, setMailId] = useState<string | null>(null);
  const [selectedItems, setSelectedItems] = useState<SelectedMailSummary[]>([]);
  const [batchItems, setBatchItems] = useState<BatchDraftItem[]>([]);
  const [snapshot, setSnapshot] = useState<MailSnapshot | null>(null);
  const [workflow, setWorkflow] = useState<MailWorkflow | null>(null);
  const [pipelineProgress, setPipelineProgress] =
    useState<PipelineProgress | null>(null);
  const [status, setStatus] = useState("Bereit.");
  const [loading, setLoading] = useState(false);

  const pollingReviewIdRef = useRef<string | null>(null);
  // The user's "open the review once it's ready" intent. Kept on a ref (not a
  // poll argument) so whichever poller wins the create-vs-resume race honors
  // it — see awaitReviewCompletion.
  const openWhenReadyRef = useRef(false);
  const statusPollTimerRef = useRef<number | null>(null);
  const batchCancelRequestedRef = useRef(false);
  const batchRunIdRef = useRef(0);

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
      setStatus(`Workflow konnte nicht geladen werden: ${String(error)}`);
      return workflow;
    }
  }

  async function loadMail() {
    setLoading(true);
    setStatus("Lade Auswahl…");
    try {
      const currentItem = Office.context?.mailbox?.item;
      setBatchItems([]);

      if (currentItem) {
        setSelectedItems([]);
        setStatus("Lade Mail…");
        const mail = await readMailSnapshot();
        const id = deriveMailId(currentItem, mail);
        const { workflow: existingWorkflow } = await loadServerWorkflow(id);
        setMailId(id);
        setSnapshot(mail);
        setWorkflow(existingWorkflow);
        setStatus("Mail geladen.");
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

      setStatus("Lade Mail…");
      const mail = await readSelectedMailSnapshot(selected[0].itemId);
      const id = deriveMailId({ itemId: selected[0].itemId }, mail);
      const { workflow: existingWorkflow } = await loadServerWorkflow(id);
      setMailId(id);
      setSnapshot(mail);
      setWorkflow(existingWorkflow);
      setStatus("Mail geladen.");
    } catch (error) {
      setStatus(`Mail konnte nicht geladen werden: ${String(error)}`);
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

  function patchBatchItemForRun(
    runId: number,
    itemId: string,
    patch: Partial<BatchDraftItem>,
  ) {
    if (batchRunIdRef.current !== runId) return;
    patchBatchItem(itemId, patch);
  }

  async function cancelBatchReviewIds(items: BatchDraftItem[]) {
    const reviewIds = Array.from(
      new Set(
        items
          .filter((item) =>
            (item.status === "loading" || item.status === "running") &&
            Boolean(item.reviewId),
          )
          .map((item) => item.reviewId as string),
      ),
    );
    await Promise.all(reviewIds.map((reviewId) => cancelReview(reviewId).catch(() => {})));
  }

  async function runBatchItem(
    item: SelectedMailSummary,
    runId: number,
  ): Promise<BatchRunOutcome> {
    if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) {
      patchBatchItemForRun(runId, item.itemId, {
        status: "cancelled",
        detail: "Pipeline gestoppt",
        error: undefined,
      });
      return "cancelled";
    }

    patchBatchItemForRun(runId, item.itemId, {
      status: "loading",
      detail: "Mail wird geladen…",
      error: undefined,
    });

    let mail: MailSnapshot;
    let itemMailId: string;
    try {
      mail = await readSelectedMailSnapshot(item.itemId);
      itemMailId = deriveMailId({ itemId: item.itemId }, mail);
    } catch (error) {
      patchBatchItemForRun(runId, item.itemId, {
        status: "failed",
        error: String(error),
      });
      return "failed";
    }

    if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) {
      patchBatchItemForRun(runId, item.itemId, {
        status: "cancelled",
        detail: "Pipeline gestoppt",
        error: undefined,
      });
      return "cancelled";
    }

    patchBatchItemForRun(runId, item.itemId, {
      status: "running",
      detail: "Startet…",
    });

    try {
      const started = await startReview(mail, itemMailId);
      patchBatchItemForRun(runId, item.itemId, {
        status: "running",
        reviewId: started.review_id,
        detail: "Läuft…",
      });

      if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) {
        await cancelReview(started.review_id).catch(() => {});
        patchBatchItemForRun(runId, item.itemId, {
          status: "cancelled",
          reviewId: started.review_id,
          detail: "Pipeline gestoppt",
          error: undefined,
        });
        return "cancelled";
      }

      const completed = await pollReviewUntilComplete(started, (progress) => {
        if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) return;
        patchBatchItemForRun(runId, item.itemId, {
          status: "running",
          detail: formatProgressStatus(progress),
        });
      });

      if (completed.status === "cancelled" || completed.progress?.status === "cancelled") {
        patchBatchItemForRun(runId, item.itemId, {
          status: "cancelled",
          reviewId: completed.review_id,
          detail: "Pipeline gestoppt",
          error: undefined,
        });
        return "cancelled";
      }

      patchBatchItemForRun(runId, item.itemId, {
        status: "completed",
        reviewId: completed.review_id,
        detail: undefined,
      });
      return "completed";
    } catch (error) {
      if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) {
        patchBatchItemForRun(runId, item.itemId, {
          status: "cancelled",
          detail: "Pipeline gestoppt",
          error: undefined,
        });
        return "cancelled";
      }
      patchBatchItemForRun(runId, item.itemId, {
        status: "failed",
        error: String(error),
      });
      return "failed";
    }
  }

  async function handleCreateBatchReviews(mode: "auto" | "restart" = "auto") {
    if (selectedItems.length === 0) return;

    const isRetry =
      mode !== "restart" &&
      batchItems.length > 0 &&
      batchItems.some((i) => i.status === "failed" || i.status === "cancelled");

    const itemsToProcess: SelectedMailSummary[] = isRetry
      ? batchItems.filter((i) => i.status === "failed" || i.status === "cancelled")
      : selectedItems;

    if (itemsToProcess.length === 0) return;

    if (mode === "restart") {
      batchCancelRequestedRef.current = true;
      await cancelBatchReviewIds(batchItems);
    }

    const runId = batchRunIdRef.current + 1;
    batchRunIdRef.current = runId;
    batchCancelRequestedRef.current = false;
    setLoading(true);
    setPipelineProgress(null);

    if (isRetry) {
      setBatchItems((items) =>
        items.map((i) =>
          i.status === "failed" || i.status === "cancelled"
            ? { ...i, status: "pending", error: undefined, detail: undefined }
            : i,
        ),
      );
      setStatus(
        itemsToProcess.length === 1
          ? "1 Mail wird wiederholt…"
          : `${itemsToProcess.length} Mails werden wiederholt…`,
      );
    } else {
      setBatchItems(
        selectedItems.map((item) => ({ ...item, status: "pending" })),
      );
      setStatus(mode === "restart" ? "Batch wird neu gestartet…" : "Reviews werden vorbereitet.");
    }

    let completedCount = isRetry
      ? batchItems.filter((i) => i.status === "completed").length
      : 0;
    let failedCount = 0;
    let cancelledCount = 0;

    const CONCURRENCY = 3;
    let cursor = 0;
    const workerCount = Math.min(CONCURRENCY, itemsToProcess.length);
    const workers = Array.from({ length: workerCount }, async () => {
      while (true) {
        if (batchCancelRequestedRef.current || batchRunIdRef.current !== runId) return;
        const index = cursor++;
        if (index >= itemsToProcess.length) return;
        const outcome = await runBatchItem(itemsToProcess[index], runId);
        if (batchRunIdRef.current !== runId) return;
        if (outcome === "completed") completedCount += 1;
        else if (outcome === "cancelled") cancelledCount += 1;
        else failedCount += 1;
      }
    });
    await Promise.all(workers);

    if (batchRunIdRef.current !== runId) return;

    const total = selectedItems.length;
    setStatus(
      cancelledCount > 0
        ? `${completedCount} von ${total} erstellt, ${cancelledCount} gestoppt.`
        : failedCount > 0
        ? `${completedCount} von ${total} erstellt, ${failedCount} fehlgeschlagen.`
        : `${completedCount} Reviews bereit.`,
    );
    setLoading(false);
  }

  async function handleRetryBatchItem(itemId: string) {
    const target = batchItems.find((i) => i.itemId === itemId);
    if (!target || (target.status !== "failed" && target.status !== "cancelled")) return;

    setLoading(true);
    setStatus("Mail wird wiederholt…");
    const runId = batchRunIdRef.current + 1;
    batchRunIdRef.current = runId;
    batchCancelRequestedRef.current = false;
    try {
      const outcome = await runBatchItem(target, runId);
      if (batchRunIdRef.current !== runId) return;
      const total = selectedItems.length;
      const completedNow =
        batchItems.filter(
          (i) => i.itemId !== itemId && i.status === "completed",
        ).length + (outcome === "completed" ? 1 : 0);
      const failedNow =
        batchItems.filter(
          (i) => i.itemId !== itemId && i.status === "failed",
        ).length + (outcome === "failed" ? 1 : 0);
      const cancelledNow =
        batchItems.filter(
          (i) => i.itemId !== itemId && i.status === "cancelled",
        ).length + (outcome === "cancelled" ? 1 : 0);
      setStatus(
        cancelledNow > 0
          ? `${completedNow} von ${total} erstellt, ${cancelledNow} gestoppt.`
          : failedNow > 0
          ? `${completedNow} von ${total} erstellt, ${failedNow} fehlgeschlagen.`
          : `${completedNow} Reviews bereit.`,
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleStopBatchPipelines() {
    if (batchItems.length === 0) return;
    batchCancelRequestedRef.current = true;
    batchRunIdRef.current += 1;
    setStatus("Batch-Pipeline wird gestoppt…");
    setBatchItems((items) =>
      items.map((item) =>
        item.status === "pending" ||
        item.status === "loading" ||
        item.status === "running"
          ? {
              ...item,
              status: "cancelled",
              detail: "Pipeline gestoppt",
              error: undefined,
            }
          : item,
      ),
    );
    await cancelBatchReviewIds(batchItems);
    setLoading(false);
    setStatus("Batch-Pipeline gestoppt.");
  }

  async function awaitReviewCompletion(
    startedReview: CreateReviewResponse,
    targetMailId: string,
    openWhenReady: boolean,
  ) {
    // Record the intent before the early-return: if another poller is already
    // running for this review, it will pick this up at completion.
    if (openWhenReady) {
      openWhenReadyRef.current = true;
    }
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
      if (completed.status === "cancelled" || completed.progress?.status === "cancelled") {
        openWhenReadyRef.current = false;
        setStatus("Pipeline gestoppt.");
      } else {
        setStatus("Review bereit.");
        const shouldOpen = openWhenReadyRef.current;
        openWhenReadyRef.current = false;
        if (shouldOpen && updated) {
          handleOpenReview(updated);
        }
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
    setStatus("Review startet…");
    try {
      const mail = snapshot ?? (await readMailSnapshot());
      setSnapshot(mail);
      const started = await startReview(mail, mailId);
      // Refresh once now so the card flips to review_running immediately;
      // pipeline polling below will pull in the completed state later.
      await refreshServerWorkflow(mailId);
      setStatus("Extraktion läuft…");
      await awaitReviewCompletion(started, mailId, openWhenReady);
    } catch (error) {
      setStatus(`Review konnte nicht erstellt werden: ${String(error)}`);
      setLoading(false);
    }
  }

  async function handleOpenReview(wf: MailWorkflow | null = workflow) {
    if (!wf?.reviewId || !mailId) {
      setStatus("Kein Review vorhanden.");
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
    setStatus("Review geöffnet.");
  }

  async function handleCreateDraftMail() {
    if (!workflow?.reviewId || !mailId) {
      setStatus("Kein Review vorhanden.");
      return;
    }
    if (workflow.state !== "approved" && workflow.state !== "quote_sent") {
      setStatus(
        "Freigabe fehlt.",
      );
      return;
    }
    setLoading(true);
    setStatus("Öffne Angebotsmail…");
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
      setStatus(`Mail konnte nicht geöffnet werden: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleResetWorkflow() {
    if (!mailId) return;
    openWhenReadyRef.current = false;
    setLoading(true);
    try {
      // Stop an in-flight run first so detaching doesn't leave an orphaned
      // pipeline churning in the background.
      if (workflow?.reviewId && workflow.state === "review_running") {
        await cancelReview(workflow.reviewId).catch(() => {});
      }
      await detachOutlookItem(mailId);
      setWorkflow(null);
      setPipelineProgress(null);
      setStatus("Neu gestartet.");
    } catch (error) {
      setStatus(`Neu starten fehlgeschlagen: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleStopPipeline() {
    if (!mailId || !workflow?.reviewId) return;
    openWhenReadyRef.current = false;
    setLoading(true);
    setStatus("Pipeline wird gestoppt…");
    try {
      await cancelReview(workflow.reviewId);
      // Reflect immediately; the active poller picks up the cancelled
      // status on its next tick and also settles the workflow state.
      setPipelineProgress((prev) =>
        prev
          ? { ...prev, status: "cancelled", error: "Pipeline manuell gestoppt" }
          : prev,
      );
      await refreshServerWorkflow(mailId);
      setStatus("Pipeline gestoppt.");
    } catch (error) {
      setStatus(`Stoppen fehlgeschlagen: ${String(error)}`);
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
        setStatus("Bitte in Outlook öffnen.");
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
        setStatus("Status wird aktualisiert…");
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
          setStatus("Review nicht mehr vorhanden.");
          return;
        }
        setStatus(`Pipeline fehlgeschlagen: ${String(error)}`);
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
          setStatus("Review nicht mehr vorhanden.");
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
          onRetryItem={handleRetryBatchItem}
          onRestartBatch={() => void handleCreateBatchReviews("restart")}
          onStopBatch={handleStopBatchPipelines}
        />
        {shouldShowStatusCard(status, false, false, false) && (
          <StatusCard status={status} loading={loading} />
        )}
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
        onStopPipeline={handleStopPipeline}
        onReloadMail={loadMail}
        onOpenOverview={() => openUrl(REVIEW_OVERVIEW_URL)}
      />

      {showStatusCard && <StatusCard status={status} loading={loading} />}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
