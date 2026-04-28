import type { ComponentType, SVGProps } from "react";
import type {
  PipelineProgress,
  PipelineStepStatus,
} from "../types";
import {
  AlertIcon,
  CheckIcon,
  ClockIcon,
  RefreshIcon,
} from "./Icons";

type Props = {
  progress: PipelineProgress | null;
};

type IconComp = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

function iconFor(status: PipelineStepStatus | string): IconComp {
  switch (status) {
    case "completed":
      return CheckIcon;
    case "running":
      return RefreshIcon;
    case "failed":
      return AlertIcon;
    default:
      return ClockIcon;
  }
}

function labelFor(status: PipelineStepStatus | string): string {
  switch (status) {
    case "completed":
      return "Erledigt";
    case "running":
      return "Läuft";
    case "failed":
      return "Fehler";
    case "skipped":
      return "Übersprungen";
    default:
      return "Offen";
  }
}

export function PipelineProgressCard({ progress }: Props) {
  if (!progress || progress.status === "completed") return null;

  const failed = progress.status === "failed";
  const steps = Array.isArray(progress.steps) ? progress.steps : [];
  const percent =
    typeof progress.progress_percent === "number"
      ? Math.max(0, Math.min(100, progress.progress_percent))
      : 0;

  return (
    <section className={`card ${failed ? "card-error" : "card-info"}`}>
      <div className="card-stack">
        <div className="row-between">
          <span className={failed ? "pill pill-danger" : "pill pill-info"}>
            <span className="pill-dot" />
            {failed ? "Pipeline-Fehler" : "Pipeline läuft"}
          </span>

          {progress.review_id && (
            <code className="review-id">{progress.review_id}</code>
          )}
        </div>

        <div>
          <div className="mail-subject">
            {progress.current_step || "Pipeline"}
          </div>

          {progress.current_detail && (
            <div className="pipeline-current-detail">
              {progress.current_detail}
            </div>
          )}
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
          <div className="pipeline-steps">
            {steps.map((step, index) => {
              const Icon = iconFor(step.status);

              return (
                <div
                  key={`${step.name}-${index}`}
                  className={`pipeline-step pipeline-step-${step.status}`}
                >
                  <Icon className="pipeline-step-icon" />

                  <div className="pipeline-step-body">
                    <div className="pipeline-step-name">
                      {step.name || "Schritt"}
                    </div>

                    {step.detail && (
                      <div className="pipeline-step-detail">
                        {step.detail}
                      </div>
                    )}
                  </div>

                  <div className="pipeline-step-status">
                    {labelFor(step.status)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {progress.error && (
          <div className="pipeline-error">{progress.error}</div>
        )}
      </div>
    </section>
  );
}