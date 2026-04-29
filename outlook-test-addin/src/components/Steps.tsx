/**
 * Steps — 4-stage progress indicator at the top of the panel.
 *
 * Mirrors the Streamlit review-detail step strip but compressed for the
 * narrow Outlook panel: just the marker + short label.
 */
import type { MailWorkflowState } from "../mailWorkflowStorage";

type StepDef = {
  key: MailWorkflowState[];
  num: string;
  title: string;
};

const STEPS: StepDef[] = [
  { key: ["new"],                              num: "01", title: "Anfrage" },
  { key: ["review_running"],                   num: "02", title: "Pipeline" },
  { key: ["review_created", "review_opened"],  num: "03", title: "Review" },
  { key: ["quote_sent"],                       num: "04", title: "Versendet" },
];

export function Steps({ workflowState }: { workflowState: MailWorkflowState }) {
  const activeIndex = STEPS.findIndex((s) => s.key.includes(workflowState));

  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        const cls =
          i < activeIndex ? "step done" :
          i === activeIndex ? "step active" :
          "step";
        const marker = i < activeIndex ? "✓" : s.num;
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
