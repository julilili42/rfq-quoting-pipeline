/**
 * Steps — 3-stage progress indicator at the top of the panel.
 *
 * Outlook flow surfaces the high-level stages: Anfrage → Pipeline →
 * Review. The internal state machine has more granularity (review_created,
 * review_opened, approved, quote_sent) but they all collapse onto the
 * same visual step — the user sees one "Review" stage that turns
 * green once the angebotsmail has been sent.
 */

import type { MailWorkflowState } from "../mailWorkflowStorage";

type StepDef = {
  key: MailWorkflowState[];
  num: string;
  title: string;
};

const STEPS: StepDef[] = [
  { key: ["new"],                                                  num: "01", title: "Anfrage" },
  { key: ["review_running"],                                       num: "02", title: "Pipeline" },
  {
    key: ["review_created", "review_opened", "approved", "quote_sent"],
    num: "03",
    title: "Review",
  },
];

export function Steps({ workflowState }: { workflowState: MailWorkflowState }) {
  const activeIndex = STEPS.findIndex((s) => s.key.includes(workflowState));
  const isQuoteSent = workflowState === "quote_sent";

  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        // quote_sent treats step 3 as fully complete (checkmark instead of
        // active pulsing). approved still shows as active because the
        // user still needs to create the angebotsmail.
        const isDone =
          i < activeIndex || (isQuoteSent && i === activeIndex);
        const isActive = i === activeIndex && !isQuoteSent;

        const cls = isDone ? "step done" : isActive ? "step active" : "step";
        const marker = isDone ? "✓" : s.num;

        return (
          <div key={s.num} className={cls}>
            <div className="step-num">{marker}</div>
            <div className="step-title">{s.title}</div>
          </div>
        );
      })}
    </div>
  );
}
