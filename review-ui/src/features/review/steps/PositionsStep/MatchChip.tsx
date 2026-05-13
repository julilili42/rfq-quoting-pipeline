import type { MatchResult, MatchStatus } from "@/shared/schemas/matchResult";
import { cn } from "@/shared/lib/cn";

const STATUS_LABEL: Record<MatchStatus, string> = {
  exact: "Exakt",
  fuzzy: "Fuzzy",
  semantic: "Semantisch",
  no_match: "Kein Treffer",
};

const STATUS_TONE: Record<MatchStatus, string> = {
  exact: "bg-success-soft text-success",
  fuzzy: "bg-info-soft text-info",
  semantic: "bg-info-soft text-info",
  no_match: "bg-warning-soft text-warning",
};

const STATUS_ACCENT: Record<MatchStatus, string> = {
  exact: "border-l-success",
  fuzzy: "border-l-info",
  semantic: "border-l-info",
  no_match: "border-l-warning",
};

export function MatchChip({
  match,
  extractedArticleNumber,
  action,
}: {
  match: MatchResult;
  extractedArticleNumber?: string | null;
  action?: React.ReactNode;
}) {
  const tone = STATUS_TONE[match.status];
  const accent = STATUS_ACCENT[match.status];
  const score =
    match.status !== "no_match" && match.score
      ? `${Math.round(match.score * 100)}%`
      : null;
  const showMatchedArticle =
    match.status !== "no_match" &&
    match.matched_artikelnr &&
    normalizeArticleNumber(match.matched_artikelnr) !==
      normalizeArticleNumber(extractedArticleNumber);

  return (
    <div
      className={cn(
        "min-w-0 rounded-md border border-border border-l-4 bg-surface px-3 py-2 text-xs",
        accent,
      )}
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5">
          <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
            Stammdaten
          </span>
          <span className={cn("inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-semibold", tone)}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            {STATUS_LABEL[match.status]}
          </span>

          {score && (
            <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-muted-foreground">
              Score {score}
            </span>
          )}

          {showMatchedArticle && (
            <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5">
              <span className="text-[10px] font-medium text-muted-foreground">Stamm</span>
              <code className="font-mono text-[11px] font-semibold text-foreground">
                {match.matched_artikelnr}
              </code>
            </span>
          )}
        </div>

        {action && <div className="shrink-0">{action}</div>}
      </div>

      <p
        className="mt-1.5 truncate text-[11px] leading-snug text-muted-foreground"
        title={match.matched_bezeichnung ?? undefined}
      >
        {match.status === "no_match"
          ? "Kein Stammdaten-Treffer vorhanden"
          : match.matched_bezeichnung || "Keine Stammdaten-Bezeichnung"}
      </p>
    </div>
  );
}

function normalizeArticleNumber(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}
