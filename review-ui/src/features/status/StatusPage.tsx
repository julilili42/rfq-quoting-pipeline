import { Link } from "react-router-dom";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { MINUTES_PER_MANUAL_REVIEW } from "@/shared/lib/constants";
import { useMetrics } from "./hooks/useMetrics";
import type { Metrics, PerReviewMetric } from "./schemas/metrics";

function fmt(n: number): string {
  return n.toLocaleString("de-DE");
}

function fmtEur(n: number): string {
  return n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
}

function fmtPct(n: number): string {
  return (n * 100).toFixed(1) + " %";
}

function fmtDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
  return `${(seconds / 86400).toFixed(1)} d`;
}

function extractionPathLabel(path: PerReviewMetric["extraction_path"]): string {
  if (path === "fast_path") return "Fast-Path";
  if (path === "llm") return "LLM";
  return "—";
}

function StatCell({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="bg-surface px-5 py-5">
      <p className="text-[11px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1.5 font-display text-xl font-semibold tracking-tight text-foreground">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground/60">{hint}</p>}
    </div>
  );
}

function PipelineStats({ m }: { m: Metrics }) {
  const avgPositions = m.total_reviews > 0 ? m.total_positions / m.total_reviews : 0;
  const completedPct = m.total_reviews > 0 ? Math.round((m.completed_reviews / m.total_reviews) * 100) : 0;
  const hoursSaved = (m.total_reviews * MINUTES_PER_MANUAL_REVIEW) / 60;
  const totalExtractions = m.fast_path_hits + m.llm_calls;
  const fastPathRate = totalExtractions > 0 ? m.fast_path_hits / totalExtractions : 0;
  const hasApprovalDuration = m.reviews_with_approval_duration > 0;

  return (
    <div className="mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
      <StatCell
        label="Angebote"
        value={m.total_reviews}
        hint={`${m.completed_reviews} abgeschlossen (${completedPct} %)`}
      />
      <StatCell
        label="Positionen"
        value={fmt(m.total_positions)}
        hint={`Ø ${avgPositions.toFixed(1)} pro Angebot`}
      />
      <StatCell
        label="Match-Quote"
        value={fmtPct(m.avg_match_rate)}
        hint="Stammdaten-Treffer"
      />
      <StatCell
        label="Gesamtvolumen"
        value={fmtEur(m.total_eur)}
      />
      <StatCell
        label="Ø Pipeline-Zeit"
        value={`${m.avg_duration_s} s`}
        hint="aktive Verarbeitung"
      />
      <StatCell
        label="Ø bis Freigabe"
        value={hasApprovalDuration ? fmtDuration(m.avg_approval_duration_s) : "—"}
        hint={hasApprovalDuration ? `${m.reviews_with_approval_duration} freigegeben` : "noch keine Freigabe"}
      />
      <StatCell
        label="Fast-Path"
        value={totalExtractions > 0 ? fmtPct(fastPathRate) : "—"}
        hint={totalExtractions > 0 ? `${m.fast_path_hits} ohne LLM, ${m.llm_calls} mit LLM` : "noch keine Daten"}
      />
      <StatCell
        label="Zeitersparnis"
        value={`${hoursSaved.toFixed(1)} h`}
        hint={`~${MINUTES_PER_MANUAL_REVIEW} min / Anfrage`}
      />
    </div>
  );
}

function TokenSummary({ m }: { m: Metrics }) {
  if (m.reviews_with_token_data === 0) return null;

  const avgInput = Math.round(m.total_input_tokens / m.reviews_with_token_data);
  const avgOutput = Math.round(m.total_output_tokens / m.reviews_with_token_data);

  return (
    <div className="mb-8 flex flex-wrap items-center gap-x-6 gap-y-1.5 rounded-lg border border-border bg-surface px-5 py-3.5 text-sm">
      <span className="font-medium text-foreground">Token</span>
      <span className="text-muted-foreground">
        Eingabe Ø{" "}
        <span className="font-semibold tabular-nums text-foreground">{fmt(avgInput)}</span>
      </span>
      <span className="text-muted-foreground">
        Ausgabe Ø{" "}
        <span className="font-semibold tabular-nums text-foreground">{fmt(avgOutput)}</span>
      </span>
      <span className="text-muted-foreground">
        Gesamt{" "}
        <span className="font-semibold tabular-nums text-foreground">{fmt(m.total_tokens)}</span>
      </span>
      <span className="ml-auto text-muted-foreground/70">
        {m.reviews_with_token_data} von {m.total_reviews} Angeboten mit Daten
      </span>
    </div>
  );
}

function PerReviewTable({ rows }: { rows: PerReviewMetric[] }) {
  const dash = "—";

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-foreground">Details pro Angebot</h2>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-[11px] font-medium text-muted-foreground">
              <th className="px-4 py-3 text-left">Betreff</th>
              <th className="px-4 py-3 text-left">Pfad</th>
              <th className="px-4 py-3 text-right">Pos.</th>
              <th className="px-4 py-3 text-right">Match-Rate</th>
              <th className="px-4 py-3 text-right">EUR</th>
              <th
                className="px-4 py-3 text-right"
                title="Summe der aktiven Verarbeitungszeiten in der Pipeline. Bei Queue-Runs aus Job claim bis complete; sonst aus gespeicherten Step-Zeiten. Ältere Reviews ohne Timing fallen auf Review-Start bis PDF-bereit zurück."
              >
                Pipeline-Zeit (s)
              </th>
              <th
                className="px-4 py-3 text-right"
                title="Zeit von Erstellung der Review bis zur finalen Freigabe."
              >
                Bis Freigabe
              </th>
              <th className="px-4 py-3 text-right">Eingabe-T</th>
              <th className="px-4 py-3 text-right">Ausgabe-T</th>
              <th className="px-4 py-3 text-right">Gesamt-T</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.review_id}
                className="border-b border-border last:border-0 transition-colors hover:bg-muted/30"
              >
                <td className="px-4 py-3">
                  <Link
                    to={`/reviews/${r.review_id}/positions`}
                    className="font-medium text-foreground hover:text-brand"
                  >
                    {r.subject || r.review_id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={
                      r.extraction_path === "fast_path"
                        ? "inline-flex rounded-md bg-success-soft px-2 py-0.5 text-[11px] font-semibold text-success"
                        : r.extraction_path === "llm"
                          ? "inline-flex rounded-md bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info"
                          : "text-muted-foreground"
                    }
                  >
                    {extractionPathLabel(r.extraction_path)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{r.positions}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtPct(r.match_rate)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{fmtEur(r.total_eur)}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {r.duration_s > 0 ? r.duration_s.toFixed(1) : dash}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtDuration(r.approval_duration_s)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                  {r.token_usage ? fmt(r.token_usage.input_tokens) : dash}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                  {r.token_usage ? fmt(r.token_usage.output_tokens) : dash}
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold">
                  {r.token_usage ? fmt(r.token_usage.total_tokens) : dash}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-sm text-muted-foreground">
                  Noch keine abgeschlossenen Angebote vorhanden.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function StatusPage() {
  const { data, isLoading, isError, error } = useMetrics();

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState error={error} />;

  return (
    <PageContainer>
      <header className="mb-8">
        <h1 className="font-display text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
          Status & Metriken<span className="text-brand">.</span>
        </h1>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
          Aggregierte Pipeline-Kennzahlen und Token-Verbrauch aller verarbeiteten Angebote.
        </p>
      </header>

      <PipelineStats m={data} />
      <TokenSummary m={data} />
      <PerReviewTable rows={data.per_review} />
    </PageContainer>
  );
}
