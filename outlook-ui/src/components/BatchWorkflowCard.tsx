import type { SelectedMailSummary } from "../outlook/mailbox";
import {
  AlertIcon,
  CheckIcon,
  ClockIcon,
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

function iconFor(status: BatchDraftStatus) {
  if (status === "completed") return CheckIcon;
  if (status === "failed") return AlertIcon;
  if (status === "pending") return ClockIcon;
  return SparkIcon;
}

function batchTitle({
  hasStarted,
  allCompleted,
  failed,
  loading,
}: {
  hasStarted: boolean;
  allCompleted: boolean;
  failed: number;
  loading: boolean;
}): string {
  if (failed > 0) return "Batch prüfen";
  if (allCompleted) return "Reviews bereit";
  if (loading || hasStarted) return "Reviews werden erstellt";
  return "Batch vorbereiten";
}

function itemDetail(item: BatchDraftItem): string {
  if (item.error) return item.error;
  if (item.status === "loading" || item.status === "running") {
    return item.detail ?? "";
  }
  return "";
}

function batchSubtitle({
  hasStarted,
  allCompleted,
  failed,
  selectionLabel,
}: {
  hasStarted: boolean;
  allCompleted: boolean;
  failed: number;
  selectionLabel: string;
}): string | null {
  if (failed > 0) return `${failed} fehlgeschlagen`;
  if (allCompleted) return null;
  if (hasStarted) return "Pipelines laufen";
  return selectionLabel;
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
  const active = items.filter(
    (item) => item.status === "loading" || item.status === "running",
  ).length;
  const total = selectedItems.length;
  const allCompleted = hasStarted && completed === total && failed === 0;
  const hasCollapsedConversations = selectedItems.some(
    (item) => item.collapsedCount > 1,
  );
  const canCreate = total > 0 && !loading;
  const progress = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;
  const listLabel = hasCollapsedConversations ? "Unterhaltungen" : "Mails";
  const selectionLabel = hasCollapsedConversations
    ? `${total} Unterhaltungen ausgewählt`
    : `${total} Mails ausgewählt`;
  const subtitle = batchSubtitle({
    hasStarted,
    allCompleted,
    failed,
    selectionLabel,
  });
  const cardClass = failed
    ? "card card-error"
    : allCompleted
      ? "card card-success"
      : "card card-info";

  return (
    <section className={cardClass}>
      <div className="card-stack">
        <div>
          <div className="mail-subject">
            {batchTitle({ hasStarted, allCompleted, failed, loading })}
          </div>
          {subtitle && <div className="mail-sender">{subtitle}</div>}
        </div>

        {hasStarted && !allCompleted && active > 0 && (
          <div className="batch-progress" aria-label={`Batch-Fortschritt ${progress}%`}>
            <div className="batch-progress-head">
              <span>{completed + failed} von {total} fertig</span>
              <strong>{progress}%</strong>
            </div>
            <div className="pipeline-progress-bar">
              <div
                className="pipeline-progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        <div className="batch-list-head">
          <span>{listLabel}</span>
        </div>
        <div className="batch-list" aria-label="Ausgewählte Mails">
          {items.map((item) => {
            const Icon = iconFor(item.status);
            const detail = itemDetail(item);
            return (
              <div
                key={item.itemId}
                className={`batch-row batch-row-${item.status}`}
              >
                <span className="batch-row-icon-wrap">
                  <Icon className="batch-row-icon" />
                </span>
                <div className="batch-row-main">
                  <div className="batch-row-title">{item.subject}</div>
                  {detail && (
                    <div className="batch-row-detail">{detail}</div>
                  )}
                </div>
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
              {hasStarted
                ? loading
                  ? "Reviews werden erstellt"
                  : "Erneut versuchen"
                : `${total} Reviews erstellen`}
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
