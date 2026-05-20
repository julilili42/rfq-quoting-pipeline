/**
 * Steps — 3-stage progress indicator at the top of the panel.
 *
 * Outlook flow surfaces the high-level stages: Anfrage → Pipeline →
 * Review. The internal state machine has more granularity (review_created,
 * review_opened, approved, quote_sent) but they all collapse onto the
 * same visual step — the user sees one "Review" stage that turns
 * complete once the angebotsmail has been sent.
 */

import type { MailWorkflowState } from "../serverWorkflow";

type StepDef = {
  key: MailWorkflowState[];
  title: string;
};

const STEPS: StepDef[] = [
  { key: ["new"],                                                  title: "Anfrage" },
  { key: ["review_running"],                                       title: "Pipeline" },
  { key: ["review_created", "review_opened", "approved", "quote_sent"], title: "Review" },
];

function CheckIcon() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="1.5,6.5 4.5,9.5 10.5,2.5" />
    </svg>
  );
}

export function Steps({ workflowState }: { workflowState: MailWorkflowState }) {
  const activeIndex = STEPS.findIndex((s) => s.key.includes(workflowState));
  const isQuoteSent = workflowState === "quote_sent";

  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        const isDone = i < activeIndex || (isQuoteSent && i === activeIndex);
        const isActive = i === activeIndex && !isQuoteSent;

        const cls = isDone ? "step done" : isActive ? "step active" : "step";

        return (
          <div key={i} className={cls}>
            {i > 0 && <div className="step-connector" />}
            <div className="step-circle">
              {isDone ? <CheckIcon /> : <span className="step-index">{i + 1}</span>}
            </div>
            <div className="step-title">{s.title}</div>
          </div>
        );
      })}
    </div>
  );
}
