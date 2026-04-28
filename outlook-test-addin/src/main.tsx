/**
 * Outlook taskpane entry point.
 *
 * The plugin is intentionally minimal: it tracks per-mail workflow
 * state and renders exactly one "next action" card based on it.
 * Everything else lives in the dashboard or behind the "Erweitert"
 * disclosure.
 */
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { createReview } from "./api/reviewApi";
import { AdvancedDetails } from "./components/AdvancedDetails";
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
import type { MailSnapshot } from "./types";
import "./style.css";

declare const Office: any;

function App() {
  const [isOutlook, setIsOutlook] = useState(false);
  const [mailId, setMailId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<MailSnapshot | null>(null);
  const [workflow, setWorkflow] = useState<MailWorkflow | null>(null);
  const [status, setStatus] = useState("Bereit. Add-in wartet auf Outlook.");
  const [loading, setLoading] = useState(false);

  // ---------- mail loading ------------------------------------------------

  async function loadMail() {
    setLoading(true);
    setStatus("Lade Mail-Inhalt und Anhänge…");
    try {
      const mail = await readMailSnapshot();
      const id = deriveMailId(Office.context?.mailbox?.item, mail);
      maybeMigrateLegacy(id);
      setMailId(id);
      setSnapshot(mail);
      setWorkflow(getWorkflow(id));
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

  // ---------- workflow transitions ---------------------------------------

  async function handleCreateReview() {
    if (!mailId) return;
    setLoading(true);
    setStatus(
      "Sende an Review-API — Extraktion kann bis zu einer Minute dauern…",
    );
    try {
      const mail = snapshot ?? (await readMailSnapshot());
      setSnapshot(mail);
      const result = await createReview(mail);
      const updated = upsertWorkflow(mailId, {
        subject: mail.subject,
        sender: mail.from,
        state: "review_created",
        review: result,
        reviewCreatedAt: new Date().toISOString(),
      });
      setWorkflow(updated);
      setStatus(`Review erstellt: ${result.review_id}. Öffne Review-UI…`);
      handleOpenReview(updated);
    } catch (error) {
      setStatus(`Fehler beim Erstellen des Reviews: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleOpenReview(wf: MailWorkflow | null = workflow) {
    if (!wf?.review || !mailId) {
      setStatus("Kein Review zur Mail vorhanden.");
      return;
    }
    openUrl(wf.review.review_url);
    const updated = upsertWorkflow(mailId, {
      state: wf.state === "new" ? "review_opened" : wf.state === "review_created" ? "review_opened" : wf.state,
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
        { subject: workflow.subject || snapshot?.subject || "" },
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
    setStatus("Workflow zurückgesetzt. Neue Anfrage bereit.");
  }

  // ---------- Office bootstrap -------------------------------------------

  useEffect(() => {
    Office.onReady((info: any) => {
      if (info.host !== Office.HostType.Outlook) {
        setIsOutlook(false);
        setStatus("Bitte über das Outlook Add-in-Manifest starten.");
        return;
      }
      setIsOutlook(true);
      loadMail();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- render ------------------------------------------------------

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
