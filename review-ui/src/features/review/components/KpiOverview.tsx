import { MetricTile } from "@/features/dashboard/components/MetricTile";
import type { Anfrage } from "@/shared/schemas/anfrage";
import type { MatchResult } from "@/shared/schemas/matchResult";
import type { Quotation } from "@/shared/schemas/quotation";
import { formatEur } from "@/shared/lib/format";

interface KpiOverviewProps {
  anfrage: Anfrage;
  matches: MatchResult[];
  quotation: Quotation | null;
  pdfReady: boolean;
}

export function KpiOverview({
  anfrage,
  matches,
  quotation,
  pdfReady,
}: KpiOverviewProps) {
  const totalPositions = anfrage.positionen.length;
  const activePosNrs = new Set(anfrage.positionen.map((p) => p.pos_nr));
  const matched = matches.filter(
    (m) => activePosNrs.has(m.pos_nr) && m.status !== "no_match",
  ).length;
  const matchRate = totalPositions > 0 ? Math.min(1, matched / totalPositions) : 0;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <MetricTile label="Positionen" value={totalPositions} />
      <MetricTile label="Match-Quote" value={`${Math.round(matchRate * 100)}%`} />
      <MetricTile
        label="Angebotssumme"
        value={quotation ? formatEur(quotation.gesamtsumme) : "—"}
      />
      <MetricTile label="PDF" value={pdfReady ? "Bereit" : "Offen"} />
    </div>
  );
}
