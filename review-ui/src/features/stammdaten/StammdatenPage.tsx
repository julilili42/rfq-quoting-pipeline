import { Database, Search } from "lucide-react";
import { useState } from "react";

import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { Input } from "@/shared/components/ui/input";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { useDebouncedValue } from "@/shared/hooks/useDebouncedValue";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

import { useStammdatenSearch } from "../review/hooks/useStammdaten";
import { StammdatenDetailDialog } from "./components/StammdatenDetailDialog";
import { StammdatenTable } from "./components/StammdatenTable";

/**
 * Read-only stammdaten browser.
 *
 * Search is a substring scan over `artikel_nr` and `bezeichnung` —
 * good enough for a few thousand rows, fast on the wire because the
 * backend caps results at 100. If the master data grows past tens
 * of thousands of rows we'd flip the backend to a paged query and
 * add a "load more" button here.
 */
export function StammdatenPage() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 250);
  const [selectedRow, setSelectedRow] = useState<StammdatenRow | null>(null);
  const { data, isLoading, isError, error } = useStammdatenSearch(
    debouncedQuery,
    true,
  );

  return (
    <PageContainer>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-extrabold tracking-tight md:text-5xl">
            Stammdaten<span className="text-brand">.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
            Suche nach Artikeln im Master-Bestand. Die Daten werden aus
            dem Quoting-Backend gelesen und sind in dieser Ansicht
            schreibgeschützt — Stammdaten-Pflege findet im SAP-Quellsystem
            statt.
          </p>
        </div>
      </header>

      <div className="mb-4 max-w-md">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Artikelnummer oder Bezeichnung…"
            className="pl-9"
            aria-label="Stammdaten durchsuchen"
            autoFocus
          />
        </div>
      </div>

      {isLoading && <LoadingState label="Lade Stammdaten…" />}

      {isError && <ErrorState error={error} />}

      {!isLoading && !isError && data && (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            <Database className="mr-1.5 inline h-3 w-3" aria-hidden="true" />
            <strong className="text-foreground">{data.length}</strong>{" "}
            {data.length === 1 ? "Treffer" : "Treffer"}
            {data.length === 100 && (
              <span className="ml-1 text-warning">
                (Limit erreicht — Suche eingrenzen für vollständige Liste)
              </span>
            )}
          </p>
          <StammdatenTable rows={data} onRowClick={setSelectedRow} />
        </>
      )}
      {selectedRow && (
        <StammdatenDetailDialog
          row={selectedRow}
          onClose={() => setSelectedRow(null)}
        />
      )}
    </PageContainer>
  );
}
