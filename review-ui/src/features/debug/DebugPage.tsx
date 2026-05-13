import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  Database,
  LayoutDashboard,
  RefreshCw,
  ShieldCheck,
  Wifi,
  XCircle,
} from "lucide-react";
import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { cn } from "@/shared/lib/cn";
import {
  type CheckResult,
  type DebugInfo,
  type LlmProbeResult,
  type PipelineFailure,
  type StammdatenQuality,
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

const NUMBER_FORMAT = new Intl.NumberFormat("de-DE");

function formatDebugDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ");
  return date.toLocaleString("de-DE", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatNumber(value: number): string {
  return NUMBER_FORMAT.format(value);
}

function stammdatenHardIssueCount(quality: StammdatenQuality | null): number {
  if (!quality) return 1;
  return (
    quality.duplicate_article_numbers +
    quality.missing_article_numbers +
    quality.missing_descriptions +
    quality.zero_or_missing_prices +
    quality.invalid_price_ranges
  );
}

function checkCounts(checks: CheckResult[]) {
  return checks.reduce(
    (acc, check) => {
      acc[check.status] += 1;
      return acc;
    },
    { ok: 0, warning: 0, error: 0 },
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4 border-b border-border pb-3">
      <h2 className="text-lg font-bold text-foreground">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function OverallBanner({ info, checkedAt }: { info: DebugInfo; checkedAt: string }) {
  const cfg = STATUS_CONFIG[info.overall];
  const Icon = cfg.icon;
  return (
    <div className={cn("mb-8 flex items-center gap-3 rounded-xl border px-5 py-4", cfg.bannerClass)}>
      <Icon className="h-5 w-5 shrink-0" aria-hidden />
      <span className="font-semibold">{cfg.bannerLabel}</span>
      <span className="ml-auto flex items-center gap-4 text-sm opacity-70">
        <span>
          Provider: <span className="font-mono font-semibold">{info.llm_provider}</span>
        </span>
        <span className="hidden opacity-40 sm:inline">|</span>
        <span className="hidden sm:inline">
          Geprüft: <span className="font-semibold">{formatDebugDate(checkedAt)}</span>
        </span>
      </span>
    </div>
  );
}

function DebugHeader({
  title,
  subtitle,
  isFetching,
  onRefresh,
}: {
  title: string;
  subtitle: string;
  isFetching: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
          {title}<span className="text-brand">.</span>
        </h1>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
          {subtitle}
        </p>
      </div>
      <button
        onClick={onRefresh}
        disabled={isFetching}
        className="mt-1 flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-semibold text-muted-foreground shadow-card transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
      >
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} aria-hidden />
        Aktualisieren
      </button>
    </header>
  );
}

function DebugNav() {
  const items = [
    { to: "/debug",            label: "Übersicht",       icon: LayoutDashboard },
    { to: "/debug/pipeline",   label: "Pipeline-Fehler", icon: Activity        },
    { to: "/debug/checks",     label: "System-Checks",   icon: ShieldCheck     },
    { to: "/debug/llm",        label: "LLM",             icon: Bot             },
    { to: "/debug/stammdaten", label: "Stammdaten",      icon: Database        },
  ];

  return (
    <nav className="mb-8 flex flex-wrap gap-2">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/debug"}
          className={({ isActive }) => cn(
            "flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-semibold shadow-card transition-colors",
            isActive
              ? "border-foreground bg-foreground text-background"
              : "border-border bg-surface text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          <item.icon className="h-4 w-4 shrink-0" aria-hidden />
          {item.label}
        </NavLink>
      ))}
    </nav>
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

function SystemChecksDisclosure({ checks }: { checks: CheckResult[] }) {
  const [open, setOpen] = useState(false);
  const counts = checkCounts(checks);
  return (
    <div className="rounded-xl border border-border bg-surface shadow-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left"
      >
        <span className="text-lg font-bold text-foreground">System-Checks</span>
        <span className="text-sm font-semibold text-muted-foreground">
          {formatNumber(counts.error)} Fehler · {formatNumber(counts.warning)} Warnungen · {formatNumber(counts.ok)} OK
        </span>
        <ChevronDown
          className={cn("ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")}
          aria-hidden
        />
      </button>
      {open && (
        <div className="border-t border-border px-5 pb-5 pt-4">
          <CheckGrid checks={checks} />
        </div>
      )}
    </div>
  );
}

function OverviewCard({
  title,
  value,
  detail,
  to,
  tone = "neutral",
  icon: Icon,
}: {
  title: string;
  value: string;
  detail: string;
  to?: string;
  tone?: "neutral" | "ok" | "warning" | "error";
  icon?: React.ElementType;
}) {
  const toneClass = {
    neutral: "border-border bg-surface",
    ok: "border-success/20 bg-success-soft",
    warning: "border-warning/20 bg-warning-soft",
    error: "border-danger/20 bg-danger-soft",
  }[tone];

  const body = (
    <div className={cn("h-full rounded-xl border p-5 shadow-card transition-colors", toneClass, to && "hover:border-foreground/20")}>
      <div className="flex items-start justify-between gap-4">
        <div>
          {Icon && <Icon className="mb-2 h-5 w-5 text-muted-foreground" aria-hidden />}
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">{value}</p>
        </div>
        {to && <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{detail}</p>
    </div>
  );

  return to ? <Link to={to}>{body}</Link> : body;
}

function DebugOverviewCards({ info }: { info: DebugInfo }) {
  const counts = checkCounts(info.checks);
  const llmCounts = checkCounts(info.checks.filter((check) => check.name.startsWith("LLM")));
  const hardIssues = stammdatenHardIssueCount(info.stammdaten_quality);
  return (
    <section className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <OverviewCard
        icon={Bot}
        title="LLM"
        value={info.llm_provider}
        detail="Provider-Konfiguration und manueller Connectivity-Test."
        to="/debug/llm"
        tone={llmCounts.error > 0 ? "error" : llmCounts.warning > 0 ? "warning" : "ok"}
      />
      <OverviewCard
        icon={Database}
        title="Stammdaten"
        value={info.stammdaten_quality ? formatNumber(info.stammdaten_quality.total_rows) : "Fehler"}
        detail={hardIssues > 0 ? `${formatNumber(hardIssues)} prüfungsrelevante Auffälligkeiten.` : "Keine kritischen Auffälligkeiten."}
        to="/debug/stammdaten"
        tone={hardIssues > 0 ? "warning" : "ok"}
      />
      <OverviewCard
        icon={Activity}
        title="Pipeline-Fehler"
        value={formatNumber(info.pipeline_failures.total_failed)}
        detail="Fehlgeschlagene Review-Läufe aus den lokalen Fortschrittsdateien."
        to="/debug/pipeline"
        tone={info.pipeline_failures.total_failed > 0 ? "warning" : "ok"}
      />
      <OverviewCard
        icon={ShieldCheck}
        title="System-Checks"
        value={`${counts.error}/${counts.warning}`}
        detail={`${formatNumber(counts.error)} Fehler, ${formatNumber(counts.warning)} Warnungen, ${formatNumber(counts.ok)} OK.`}
        to="/debug/checks"
        tone={counts.error > 0 ? "error" : counts.warning > 0 ? "warning" : "ok"}
      />
    </section>
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
          <dd className="mt-1 font-semibold text-foreground">{formatDebugDate(result.checked_at)}</dd>
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

function PipelineTable({ failures, total }: { failures: PipelineFailure[]; total: number }) {
  if (failures.length === 0) {
    return (
      <div className="rounded-xl border border-success/20 bg-success-soft px-5 py-4 text-sm font-semibold text-success">
        Keine fehlgeschlagenen Pipeline-Läufe gefunden.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Schritt
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Betreff / Fehler
            </th>
            <th className="hidden px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground sm:table-cell">
              Absender
            </th>
            <th className="hidden px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground md:table-cell">
              %
            </th>
            <th className="hidden px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground lg:table-cell">
              Aktualisiert
            </th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {failures.map((failure) => (
            <tr key={failure.review_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 align-top">
                <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger whitespace-nowrap">
                  {failure.current_step}
                </span>
              </td>
              <td className="px-4 py-3 align-top">
                <p className="max-w-xs truncate font-medium text-foreground">{failure.subject}</p>
                <p className="mt-0.5 max-w-xs truncate font-mono text-[11px] text-muted-foreground">
                  {failure.error}
                </p>
              </td>
              <td className="hidden px-4 py-3 align-top sm:table-cell">
                <p className="max-w-[180px] truncate text-xs text-muted-foreground">
                  {failure.sender ?? "—"}
                </p>
              </td>
              <td className="hidden px-4 py-3 text-right align-top md:table-cell">
                <span className="text-xs font-semibold text-foreground">{failure.progress_percent}%</span>
              </td>
              <td className="hidden px-4 py-3 align-top lg:table-cell">
                <span className="text-xs text-muted-foreground">{formatDebugDate(failure.updated_at)}</span>
              </td>
              <td className="px-4 py-3 text-right align-top">
                <Link
                  to={`/reviews/${encodeURIComponent(failure.review_id)}`}
                  className="rounded border border-border px-2 py-1 text-xs font-semibold text-foreground transition-colors hover:bg-muted"
                >
                  Öffnen
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {total > failures.length && (
        <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">
          Zeigt {failures.length} von {formatNumber(total)} fehlgeschlagenen Läufen.
        </p>
      )}
    </div>
  );
}

function QualityMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "ok" | "warning" | "error";
}) {
  const toneClass = {
    neutral: "border-border bg-surface text-foreground",
    ok: "border-success/20 bg-success-soft text-success",
    warning: "border-warning/20 bg-warning-soft text-warning",
    error: "border-danger/20 bg-danger-soft text-danger",
  }[tone];

  return (
    <div className={cn("rounded-xl border p-4 shadow-card", toneClass)}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-75">{label}</p>
      <p className="mt-2 text-2xl font-extrabold leading-none">
        {typeof value === "number" ? formatNumber(value) : value}
      </p>
    </div>
  );
}

function StammdatenQualitySection({ quality }: { quality: StammdatenQuality | null }) {
  if (!quality) {
    return (
      <section className="mb-8">
        <SectionHeader title="Stammdaten-Qualität" />
        <div className="rounded-xl border border-danger/20 bg-danger-soft px-5 py-4 text-sm font-semibold text-danger">
          stammdaten.csv konnte nicht gelesen werden.
        </div>
      </section>
    );
  }

  const hardIssues =
    quality.duplicate_article_numbers +
    quality.missing_article_numbers +
    quality.missing_descriptions +
    quality.zero_or_missing_prices +
    quality.invalid_price_ranges;

  return (
    <section className="mb-8">
      <div className="flex items-end justify-between gap-4">
        <SectionHeader
          title="Stammdaten-Qualität"
          subtitle={`${quality.path} · ${quality.file_size_kb} KB · geändert ${formatDebugDate(quality.last_modified)}`}
        />
        <span className={cn(
          "mb-4 w-fit shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
          hardIssues > 0 ? "bg-warning-soft text-warning" : "bg-success-soft text-success",
        )}>
          {hardIssues > 0 ? `${formatNumber(hardIssues)} Auffälligkeiten` : "Keine kritischen Auffälligkeiten"}
        </span>
      </div>

      <div className="mb-6">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Auffälligkeiten
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <QualityMetric label="Duplikate"             value={quality.duplicate_article_numbers} tone={quality.duplicate_article_numbers ? "warning" : "ok"} />
          <QualityMetric label="Artikelnummer fehlt"   value={quality.missing_article_numbers}   tone={quality.missing_article_numbers   ? "error"   : "ok"} />
          <QualityMetric label="Bezeichnung fehlt"     value={quality.missing_descriptions}      tone={quality.missing_descriptions      ? "error"   : "ok"} />
          <QualityMetric label="Preis 0/leer"          value={quality.zero_or_missing_prices}    tone={quality.zero_or_missing_prices    ? "warning" : "ok"} />
          <QualityMetric label="Preisbereich ungültig" value={quality.invalid_price_ranges}      tone={quality.invalid_price_ranges      ? "warning" : "ok"} />
        </div>
      </div>

      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Statistiken
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <QualityMetric label="Artikel gesamt"     value={quality.total_rows}            tone="neutral" />
          <QualityMetric label="Nur 1 Angebot"      value={quality.single_offer_articles} tone="neutral" />
          <QualityMetric label="Abmessungen fehlen" value={quality.missing_dimensions}    tone="neutral" />
        </div>
      </div>

      {(quality.sample_duplicate_articles.length > 0 || quality.sample_zero_price_articles.length > 0) && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {quality.sample_duplicate_articles.length > 0 && (
            <div className="rounded-xl border border-warning/20 bg-surface p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Beispiel-Duplikate</p>
              <p className="mt-2 break-all font-mono text-sm text-foreground">
                {quality.sample_duplicate_articles.join(", ")}
              </p>
            </div>
          )}
          {quality.sample_zero_price_articles.length > 0 && (
            <div className="rounded-xl border border-warning/20 bg-surface p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Beispiele Preis 0/leer</p>
              <p className="mt-2 break-all font-mono text-sm text-foreground">
                {quality.sample_zero_price_articles.join(", ")}
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function LlmProviderSection({ checks }: { checks: CheckResult[] }) {
  const llmProbe = useLlmProbe();

  return (
    <>
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

      <section>
        <SectionHeader title="Konfiguration" />
        <CheckGrid checks={checks} />
      </section>
    </>
  );
}

function DebugDataBoundary({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: (data: DebugInfo) => React.ReactNode;
}) {
  const { data, isLoading, isError, error, refetch, isFetching } = useDebug();

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState error={error} />;

  return (
    <PageContainer>
      <DebugHeader
        title={title}
        subtitle={subtitle}
        isFetching={isFetching}
        onRefresh={() => refetch()}
      />
      <DebugNav />
      {children(data)}
    </PageContainer>
  );
}

export function DebugPage() {
  return (
    <DebugDataBoundary
      title="System-Diagnose"
      subtitle="Kurzüberblick über Systemzustand, Pipeline-Fehler und wichtige Konfigurationschecks."
    >
      {(data) => (
        <>
          <OverallBanner info={data} checkedAt={data.checked_at} />
          <DebugOverviewCards info={data} />
        </>
      )}
    </DebugDataBoundary>
  );
}

export function DebugPipelinePage() {
  return (
    <DebugDataBoundary
      title="Pipeline-Fehler"
      subtitle="Fehlgeschlagene Review-Läufe aus den lokalen Fortschrittsdateien."
    >
      {(data) => (
        <section>
          <div className="flex items-end justify-between gap-4">
            <SectionHeader
              title="Fehlgeschlagene Läufe"
              subtitle="Die 5 zuletzt fehlgeschlagenen Reviews."
            />
            <span className={cn(
              "mb-4 w-fit shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
              data.pipeline_failures.total_failed > 0 ? "bg-warning-soft text-warning" : "bg-success-soft text-success",
            )}>
              {formatNumber(data.pipeline_failures.total_failed)} Fehler gesamt
            </span>
          </div>
          <PipelineTable
            failures={data.pipeline_failures.recent}
            total={data.pipeline_failures.total_failed}
          />
        </section>
      )}
    </DebugDataBoundary>
  );
}

export function DebugChecksPage() {
  return (
    <DebugDataBoundary
      title="System-Checks"
      subtitle="Alle Konfigurationsüberprüfungen im Detail."
    >
      {(data) => {
        const counts = checkCounts(data.checks);
        return (
          <section>
            <div className="flex items-end justify-between gap-4">
              <SectionHeader
                title="Alle Checks"
                subtitle={`${formatNumber(data.checks.length)} Checks insgesamt.`}
              />
              <span className={cn(
                "mb-4 w-fit shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
                counts.error > 0 ? "bg-danger-soft text-danger" : counts.warning > 0 ? "bg-warning-soft text-warning" : "bg-success-soft text-success",
              )}>
                {counts.error > 0
                  ? `${formatNumber(counts.error)} Fehler`
                  : counts.warning > 0
                  ? `${formatNumber(counts.warning)} Warnungen`
                  : "Alle OK"}
              </span>
            </div>
            <CheckGrid checks={data.checks} />
          </section>
        );
      }}
    </DebugDataBoundary>
  );
}

export function DebugLlmPage() {
  return (
    <DebugDataBoundary
      title="LLM-Diagnose"
      subtitle="Provider-Konfiguration prüfen und einen expliziten Connectivity-Test ausführen."
    >
      {(data) => (
        <LlmProviderSection
          checks={data.checks.filter((check) =>
            check.name.startsWith("LLM") || check.name === ".env Datei"
          )}
        />
      )}
    </DebugDataBoundary>
  );
}

export function DebugStammdatenPage() {
  return (
    <DebugDataBoundary
      title="Stammdaten-Diagnose"
      subtitle="Datenqualität der lokalen Artikelstammdaten prüfen."
    >
      {(data) => (
        <>
          <StammdatenQualitySection quality={data.stammdaten_quality} />
          <section>
            <SectionHeader title="Zugehörige Checks" />
            <CheckGrid
              checks={data.checks.filter((check) =>
                check.name.includes("Stammdaten") || check.name === "stammdaten.csv"
              )}
            />
          </section>
        </>
      )}
    </DebugDataBoundary>
  );
}
