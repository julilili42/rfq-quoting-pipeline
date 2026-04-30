/**
 * Steps — 3-stage progress indicator at the top of the panel.
 *
 * The Outlook flow surfaces the high-level stages: Anfrage → Pipeline →
 * Review. The previous fourth step "Versendet" added no clear value:
 * sending happens implicitly when the user hands the draft mail off to
 * Outlook. The 5-state internal machine still exists in storage; we
 * just collapse the three "review-side" states (review_created,
 * review_opened, quote_sent) onto the same visual step.
 */
import type { MailWorkflowState } from "../mailWorkflowStorage";

type StepDef = {
  key: MailWorkflowState[];
  num: string;
  title: string;
};

const STEPS: StepDef[] = [
  { key: ["new"],                                                num: "01", title: "Anfrage" },
  { key: ["review_running"],                                     num: "02", title: "Pipeline" },
  { key: ["review_created", "review_opened", "quote_sent"],      num: "03", title: "Review" },
];

export function Steps({ workflowState }: { workflowState: MailWorkflowState }) {
  const activeIndex = STEPS.findIndex((s) => s.key.includes(workflowState));
  const isQuoteSent = workflowState === "quote_sent";

  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        // quote_sent is treated as "step 3 fully complete" so the Review
        // step shows a checkmark instead of the active pulsing state.
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
