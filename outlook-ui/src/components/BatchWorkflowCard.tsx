import type { SelectedMailSummary } from "../outlook/mailbox";
import {
  AlertIcon,
  CheckIcon,
  ExternalIcon,
  RefreshIcon,
  SparkIcon,
} from "./Icons";

export type BatchDraftStatus =
  | "pending"
  | "loading"
  | "running"
  | "completed"
  | "failed";

export type BatchDraftItem = SelectedMailSummary & {
  status: BatchDraftStatus;
  reviewId?: string;
  detail?: string;
  error?: string;
};

type BatchWorkflowCardProps = {
  selectedItems: SelectedMailSummary[];
  batchItems: BatchDraftItem[];
  loading: boolean;
  onCreateBatch: () => void;
  onReloadSelection: () => void;
  onOpenOverview: () => void;
};

function labelFor(status: BatchDraftStatus): string {
  switch (status) {
    case "pending":
      return "Wartet";
    case "loading":
      return "Lädt Mail";
    case "running":
      return "Pipeline";
    case "completed":
      return "Erstellt";
    case "failed":
      return "Fehler";
  }
}

function iconFor(status: BatchDraftStatus) {
  if (status === "completed") return CheckIcon;
  if (status === "failed") return AlertIcon;
  return SparkIcon;
}

export function BatchWorkflowCard({
  selectedItems,
  batchItems,
  loading,
  onCreateBatch,
  onReloadSelection,
  onOpenOverview,
}: BatchWorkflowCardProps) {
  const items: BatchDraftItem[] = batchItems.length > 0
    ? batchItems
    : selectedItems.map((item) => ({ ...item, status: "pending" }));
  const hasStarted = batchItems.length > 0;
  const completed = items.filter((item) => item.status === "completed").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const total = selectedItems.length;
  const allCompleted = hasStarted && completed === total && failed === 0;
  const hasCollapsedConversations = selectedItems.some(
    (item) => item.collapsedCount > 1,
  );
  const canCreate = total > 0 && !loading;
  const selectionLabel = hasCollapsedConversations
    ? `${total} Unterhaltungen ausgewählt`
    : `${total} Mails ausgewählt`;
  const cardClass = failed
    ? "card card-error"
    : allCompleted
      ? "card card-success"
      : "card card-info";

  return (
    <section className={cardClass}>
      <div className="card-stack">
        <div className="row-between">
          <span className="pill pill-info">
            <span className="pill-dot" />
            {selectionLabel}
          </span>
        </div>

        <div>
          <div className="mail-subject">
            {allCompleted ? "Batch-Drafts erstellt" : "Batch-Drafts erstellen"}
          </div>
        </div>

        <div className="batch-list" aria-label="Ausgewählte Mails">
          {items.map((item) => {
            const Icon = iconFor(item.status);
            const detail =
              item.reviewId ??
              item.error ??
              item.detail ??
              (hasStarted ? labelFor(item.status) : "");
            return (
              <div
                key={item.itemId}
                className={`batch-row batch-row-${item.status} ${
                  hasStarted ? "" : "batch-row-idle"
                }`}
              >
                <Icon className="batch-row-icon" />
                <div className="batch-row-main">
                  <div className="batch-row-title">{item.subject}</div>
                  {detail && (
                    <div className="batch-row-detail">{detail}</div>
                  )}
                </div>
                {hasStarted && (
                  <span className="batch-row-status">
                    {labelFor(item.status)}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <div className="actions">
          {allCompleted ? (
            <button
              className="btn btn-primary"
              disabled={loading}
              onClick={onOpenOverview}
            >
              <ExternalIcon className="btn-icon" />
              Übersicht öffnen
            </button>
          ) : (
            <button
              className="btn btn-primary"
              disabled={!canCreate}
              onClick={onCreateBatch}
            >
              <SparkIcon className="btn-icon" />
              {total} Drafts erstellen
            </button>
          )}
          <button
            className="btn btn-ghost"
            disabled={loading}
            onClick={onReloadSelection}
          >
            <RefreshIcon className="btn-icon" />
            Auswahl aktualisieren
          </button>
        </div>
      </div>
    </section>
  );
}
