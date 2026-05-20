import {
  Award,
  CalendarClock,
  FileSearch,
  Info,
  Package,
  Truck,
  type LucideIcon,
} from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { Checkbox } from "@/shared/components/ui/checkbox";
import { cn } from "@/shared/lib/cn";
import type {
  Anforderung,
  AnforderungKategorie,
} from "@/shared/schemas/anfrage";

import { useAcknowledgeRequirements } from "../../hooks/useReviewMutations";

interface RequirementsChecklistProps {
  anforderungen: Anforderung[];
  acknowledgedIndices: number[];
}

const KATEGORIE_META: Record<
  AnforderungKategorie,
  { label: string; icon: LucideIcon }
> = {
  zeichnung: { label: "Zeichnung", icon: FileSearch },
  zertifikat: { label: "Zertifikat", icon: Award },
  verpackung: { label: "Verpackung", icon: Package },
  logistik: { label: "Logistik", icon: Truck },
  termin: { label: "Termin", icon: CalendarClock },
  sonstige: { label: "Sonstige", icon: Info },
};

export function RequirementsChecklist({
  anforderungen,
  acknowledgedIndices,
}: RequirementsChecklistProps) {
  const { reviewId } = useParams<{ reviewId: string }>();
  const mutate = useAcknowledgeRequirements(reviewId);

  const ackSet = useMemo(() => new Set(acknowledgedIndices), [acknowledgedIndices]);

  if (anforderungen.length === 0) return null;

  const ackedCount = anforderungen.filter((_, idx) => ackSet.has(idx)).length;
  const allAcked = ackedCount === anforderungen.length;

  const toggle = (idx: number) => {
    const next = new Set(ackSet);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    mutate.mutate(Array.from(next));
  };

  return (
    <div
      className={cn(
        "mt-3 rounded-md border p-3",
        allAcked
          ? "border-success/30 bg-success-soft/30"
          : "border-warning/30 bg-warning-soft",
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <p
          className={cn(
            "text-xs font-bold uppercase tracking-wide",
            allAcked ? "text-success" : "text-warning",
          )}
        >
          Besondere Anforderungen ({ackedCount}/{anforderungen.length})
        </p>
        <p className="text-[11px] text-muted-foreground">aus der Anfrage extrahiert</p>
      </div>
      <ul className="space-y-1.5">
        {anforderungen.map((item, idx) => (
          <RequirementRow
            key={`${idx}-${item.text}`}
            item={item}
            checked={ackSet.has(idx)}
            onToggle={() => toggle(idx)}
          />
        ))}
      </ul>
    </div>
  );
}

function RequirementRow({
  item,
  checked,
  onToggle,
}: {
  item: Anforderung;
  checked: boolean;
  onToggle: () => void;
}) {
  const meta = KATEGORIE_META[item.kategorie] ?? KATEGORIE_META.sonstige;
  const Icon = meta.icon;
  return (
    <li className="flex items-start gap-2 rounded-md bg-surface/60 px-2 py-1.5">
      <Checkbox
        checked={checked}
        onCheckedChange={onToggle}
        ariaLabel={`${item.text} bestätigen`}
        className="mt-0.5"
      />
      <Icon
        className={cn(
          "mt-0.5 h-4 w-4 shrink-0",
          checked ? "text-success" : "text-muted-foreground",
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span
            className={cn(
              "text-sm font-medium",
              checked && "text-muted-foreground line-through",
            )}
          >
            {item.text}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {meta.label}
          </span>
          {typeof item.pos_nr === "number" && (
            <PositionLink posNr={item.pos_nr} />
          )}
        </div>
        {item.source_quote && (
          <p className="mt-0.5 text-[11px] italic leading-snug text-muted-foreground">
            „{item.source_quote}"
          </p>
        )}
      </div>
    </li>
  );
}

function PositionLink({ posNr }: { posNr: number }) {
  const { reviewId } = useParams<{ reviewId: string }>();
  if (!reviewId) return <span className="text-[11px] text-muted-foreground">→ Pos {posNr}</span>;
  return (
    <Link
      to={`/reviews/${reviewId}/positions#pos-${posNr}`}
      className="text-[11px] text-brand hover:underline"
    >
      → Pos {posNr}
    </Link>
  );
}
