import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { useDebouncedValue } from "@/shared/hooks/useDebouncedValue";
import { formatEur } from "@/shared/lib/format";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

import {
  useMatchOverride,
  useStammdatenSearch,
} from "../../hooks/useStammdaten";

interface StammdatenSearchDialogProps {
  reviewId: string;
  posNr: number;
  /**
   * Pre-fill the search box with the position's article number when
   * opened — gives the user a starting point if the auto-match got
   * close but not exact.
   */
  initialQuery?: string;
  /** Trigger element. Required because the dialog has no default look. */
  children: React.ReactNode;
}

/**
 * Manual re-match dialog.
 *
 * Self-contained: the parent supplies the trigger, the dialog handles
 * search, override mutation, and dismissal. After a successful pin,
 * the dialog closes itself and React Query invalidation in
 * `useMatchOverride` causes the parent to re-render with the new
 * match — there's nothing for the caller to wire up.
 */
export function StammdatenSearchDialog({
  reviewId,
  posNr,
  initialQuery,
  children,
}: StammdatenSearchDialogProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(initialQuery ?? "");
  const debouncedQuery = useDebouncedValue(query, 250);

  // Reset the query each time the dialog opens so a stale search from
  // the last position doesn't leak in.
  useEffect(() => {
    if (open) setQuery(initialQuery ?? "");
  }, [open, initialQuery]);

  const search = useStammdatenSearch(debouncedQuery, open);
  const override = useMatchOverride(reviewId);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Position {posNr} · Artikel zuordnen</DialogTitle>
          <DialogDescription>
            Suche nach Artikelnummer oder Bezeichnung. Die ausgewählte
            Zeile wird als manueller Treffer hinterlegt; das PDF wird
            anschließend neu berechnet.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Artikelnummer oder Bezeichnung"
            className="pl-9"
            autoFocus
          />
        </div>

        <div className="max-h-96 overflow-y-auto">
          {search.isLoading && <LoadingState label="Suche…" />}
          {search.isError && <ErrorState error={search.error} />}
          {search.data && search.data.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Keine Treffer für „{debouncedQuery}".
            </p>
          )}
          {search.data && search.data.length > 0 && (
            <ul className="divide-y divide-border">
              {search.data.map((row) => (
                <ResultRow
                  key={row.artikel_nr}
                  row={row}
                  pending={override.isPending}
                  onPin={() =>
                    override.mutate(
                      { posNr, artikelNr: row.artikel_nr },
                      { onSuccess: () => setOpen(false) },
                    )
                  }
                />
              ))}
            </ul>
          )}
        </div>

        {override.isError && <ErrorState error={override.error} />}
      </DialogContent>
    </Dialog>
  );
}

function ResultRow({
  row,
  pending,
  onPin,
}: {
  row: StammdatenRow;
  pending: boolean;
  onPin: () => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
            {row.artikel_nr}
          </code>
          <span className="text-xs text-muted-foreground">
            {row.einheit} · {formatEur(row.basispreis_eur)}
          </span>
        </div>
        <div className="mt-1 truncate text-sm font-medium">
          {row.bezeichnung || "—"}
        </div>
        {(row.werkstoff || row.abmessungen) && (
          <div className="mt-0.5 truncate text-xs text-muted-foreground">
            {[row.werkstoff, row.abmessungen].filter(Boolean).join(" · ")}
          </div>
        )}
      </div>
      <Button variant="primary" size="sm" onClick={onPin} disabled={pending}>
        {pending ? "Übernehme…" : "Zuordnen"}
      </Button>
    </li>
  );
}
