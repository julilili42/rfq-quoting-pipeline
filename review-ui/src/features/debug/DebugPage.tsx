import { AlertTriangle, CheckCircle2, RefreshCw, Wifi, XCircle } from "lucide-react";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { cn } from "@/shared/lib/cn";
import {
  type CheckResult,
  type DebugInfo,
  type LlmProbeResult,
  useDebug,
  useLlmProbe,
} from "./useDebug";

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

const STATUS_CONFIG = {
  ok: {
    icon: CheckCircle2,
    iconClass: "text-success",
    badgeClass: "bg-success-soft text-success",
    badgeLabel: "OK",
    bannerClass: "bg-success-soft border-success/20 text-success",
    bannerLabel: "Alle Checks bestanden",
  },
  warning: {
    icon: AlertTriangle,
    iconClass: "text-warning",
    badgeClass: "bg-warning-soft text-warning",
    badgeLabel: "Warnung",
    bannerClass: "bg-warning-soft border-warning/20 text-warning",
    bannerLabel: "Hinweise vorhanden",
  },
  error: {
    icon: XCircle,
    iconClass: "text-danger",
    badgeClass: "bg-danger-soft text-danger",
    badgeLabel: "Fehler",
    bannerClass: "bg-danger-soft border-danger/20 text-danger",
    bannerLabel: "Kritische Probleme gefunden",
  },
} as const;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function OverallBanner({ info }: { info: DebugInfo }) {
  const cfg = STATUS_CONFIG[info.overall];
  const Icon = cfg.icon;
  return (
    <div className={cn("mb-8 flex items-center gap-3 rounded-xl border px-5 py-4", cfg.bannerClass)}>
      <Icon className="h-5 w-5 shrink-0" aria-hidden />
      <span className="font-semibold">{cfg.bannerLabel}</span>
      <span className="ml-auto text-sm opacity-70">
        Provider: <span className="font-mono font-semibold">{info.llm_provider}</span>
      </span>
    </div>
  );
}

function CheckCard({ check }: { check: CheckResult }) {
  const cfg = STATUS_CONFIG[check.status];
  const Icon = cfg.icon;
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-card">
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", cfg.iconClass)} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground leading-snug">{check.name}</p>
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold", cfg.badgeClass)}>
          {cfg.badgeLabel}
        </span>
      </div>
      <p className="text-sm text-muted-foreground break-all leading-relaxed pl-8">{check.detail}</p>
    </div>
  );
}

function CheckGrid({ checks }: { checks: CheckResult[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {checks.map((c) => (
        <CheckCard key={c.name} check={c} />
      ))}
    </div>
  );
}

function LlmProbeCard({ result }: { result: LlmProbeResult }) {
  const cfg = STATUS_CONFIG[result.status];
  const Icon = cfg.icon;

  return (
    <div className="mt-4 rounded-xl border border-border bg-surface p-5 shadow-card">
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", cfg.iconClass)} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">LLM-Verbindungstest</p>
            <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-semibold", cfg.badgeClass)}>
              {cfg.badgeLabel}
            </span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{result.detail}</p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Provider</dt>
          <dd className="mt-1 font-mono font-semibold text-foreground">{result.provider}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Modell</dt>
          <dd className="mt-1 break-all font-mono font-semibold text-foreground">{result.model}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Latenz</dt>
          <dd className="mt-1 font-semibold text-foreground">{result.latency_ms} ms</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Zeitpunkt</dt>
          <dd className="mt-1 font-semibold text-foreground">{result.checked_at.replace("T", " ")}</dd>
        </div>
      </dl>

      {result.error_type && (
        <p className="mt-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 font-mono text-xs leading-relaxed text-danger">
          {result.error_type}: {result.detail}
        </p>
      )}

      {result.response_preview && (
        <pre className="mt-4 max-h-40 overflow-auto rounded-lg border border-border bg-muted p-3 text-xs leading-relaxed text-foreground">
          {result.response_preview}
        </pre>
      )}

      {result.usage && (
        <p className="mt-3 text-xs text-muted-foreground">
          Tokens: {result.usage.input_tokens} Input · {result.usage.output_tokens} Output · {result.usage.total_tokens} Gesamt
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function DebugPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useDebug();
  const llmProbe = useLlmProbe();

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState error={error} />;

  return (
    <PageContainer>
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
            System-Diagnose<span className="text-brand">.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
            Konfiguration und Systemvoraussetzungen auf einen Blick.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="mt-1 flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-semibold text-muted-foreground shadow-card transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} aria-hidden />
          Aktualisieren
        </button>
      </header>

      <OverallBanner info={data} />

      <section className="mb-8">
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-card sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-base font-bold text-foreground">LLM Provider</h2>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              Erreichbarkeitstest für den konfigurierten Provider mit minimalem Prompt.
            </p>
          </div>
          <button
            onClick={() => llmProbe.mutate()}
            disabled={llmProbe.isPending}
            className="flex shrink-0 items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-semibold text-foreground shadow-card transition-colors hover:bg-muted disabled:opacity-50"
          >
            {llmProbe.isPending ? (
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Wifi className="h-4 w-4" aria-hidden />
            )}
            Provider testen
          </button>
        </div>

        {llmProbe.isError && (
          <p className="mt-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 text-sm font-semibold text-danger">
            Debug-Endpoint nicht erreichbar: {llmProbe.error instanceof Error ? llmProbe.error.message : "Unbekannter Fehler"}
          </p>
        )}

        {llmProbe.data && <LlmProbeCard result={llmProbe.data} />}
      </section>

      <CheckGrid checks={data.checks} />

      <p className="mt-6 text-right text-xs text-muted-foreground/60">
        Geprüft um {data.checked_at.replace("T", " ")}
      </p>
    </PageContainer>
  );
}
