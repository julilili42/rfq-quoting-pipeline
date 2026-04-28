/**
 * Step indicator — 3 business stages aligned with the Streamlit review UI.
 */

import type { MailWorkflowState } from "../mailWorkflowStorage";

type StepsProps = {
  workflowState: MailWorkflowState;
};

const STEPS = [
  { num: 1, label: "Anfrage" },
  { num: 2, label: "Angebot" },
  { num: 3, label: "Versand" },
] as const;

function activeIndex(state: MailWorkflowState): number {
  switch (state) {
    case "new":
      return 0;

    case "review_running":
    case "review_created":
    case "review_opened":
      return 1;

    case "quote_sent":
      return 2;
  }
}

export function Steps({ workflowState }: StepsProps) {
  const current = activeIndex(workflowState);
  const allDone = workflowState === "quote_sent";

  return (
    <div className="steps" role="list" aria-label="Workflow-Fortschritt">
      {STEPS.map((step, index) => {
        const status =
          allDone || index < current
            ? "done"
            : index === current
              ? "active"
              : "idle";

        return (
          <div
            key={step.num}
            role="listitem"
            className={`step ${status}`}
            aria-current={status === "active" ? "step" : undefined}
          >
            <div className="step-num">
              {status === "done" ? "✓" : step.num}
            </div>
            <div className="step-label">{step.label}</div>
          </div>
        );
      })}
    </div>
  );
}