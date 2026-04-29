/**
 * StatusCard — single-line status display for the panel.
 *
 * Sits below the WorkflowCard. Shows the latest action result and a
 * spinner when the panel is busy.
 */
type StatusCardProps = {
  status: string;
  loading: boolean;
};

export function StatusCard({ status, loading }: StatusCardProps) {
  return (
    <div className={`status-card ${loading ? "loading" : ""}`}>
      {loading && <div className="status-spinner" aria-hidden="true" />}
      <span>{status}</span>
    </div>
  );
}
