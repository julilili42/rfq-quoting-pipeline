/**
 * Outlook taskpane entry point.
 */

import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import {
  pollReviewUntilComplete,
  startReview,
} from "./api/reviewApi";
import { AdvancedDetails } from "./components/AdvancedDetails";
import { PipelineProgressCard } from "./components/PipelineProgressCard";
import { StatusCard } from "./components/StatusCard";
import { Steps } from "./components/Steps";
import { WorkflowCard } from "./components/WorkflowCard";
import { createDraftMail, openUrl } from "./outlook/draftMail";
import { readMailSnapshot } from "./outlook/mailbox";
import {
  type MailWorkflow,
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

import "./style.css";

declare const Office: any;

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

    openUrl(wf.review.review_url);

    const nextState =
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

    setLoading(true);
    setStatus("Öffne Angebotsmail mit aktueller PDF…");

    try {
      await createDraftMail(
        workflow.review,
        {
          subject: workflow.subject || snapshot?.subject || "",
        },
        setStatus,
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

  useEffect(() => {
    Office.onReady((info: any) => {
      console.log("Office.onReady info:", info);
      console.log("Office.HostType:", Office.HostType);
      console.log("Mailbox item:", Office.context?.mailbox?.item);

      if (info.host !== Office.HostType.Outlook) {
        setIsOutlook(false);
        setStatus(
          `Nicht im Outlook-Host gestartet. info.host=${String(info.host)}, Outlook=${String(Office.HostType?.Outlook)}`
        );
        return;
      }

      setIsOutlook(true);
      loadMail();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

      await awaitReviewCompletion(
        currentReview,
        currentMailId,
        false,
      );
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

  return (
    <div className="panel">
      <Steps workflowState={workflow?.state ?? "new"} />

      <WorkflowCard
        workflow={workflow}
        snapshot={snapshot}
        isOutlook={isOutlook}
        loading={loading}
        onCreateReview={handleCreateReview}
        onOpenReview={() => handleOpenReview()}
        onCreateDraftMail={handleCreateDraftMail}
        onResetWorkflow={handleResetWorkflow}
        onReloadMail={loadMail}
      />

      <PipelineProgressCard progress={pipelineProgress} />

      <StatusCard status={status} loading={loading} />

      <AdvancedDetails snapshot={snapshot} />

      <div className="footer-note">
        Übersicht aller Vorgänge in der{" "}
        <a
          className="footer-link"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            openUrl("http://localhost:8501");
          }}
        >
          Quoting-Übersicht
        </a>
        .
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);