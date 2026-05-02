import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo } from "react";

import { formatEur } from "@/shared/lib/format";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

interface StammdatenTableProps {
  rows: StammdatenRow[];
  /** Optional row-click handler — useful for picking-style flows later. */
  onRowClick?: (row: StammdatenRow) => void;
}

/**
 * Read-only stammdaten preview.
 *
 * Renders a compact, scrollable table with sticky headers. Row data
 * itself is small (~6 columns) so we don't bother with virtual rows;
 * if the master data grows past a few thousand rows we'd swap the
 * `useReactTable` body for `@tanstack/react-virtual`.
 */
export function StammdatenTable({ rows, onRowClick }: StammdatenTableProps) {
  const columns = useMemo<ColumnDef<StammdatenRow>[]>(
    () => [
      {
        id: "artikel_nr",
        header: "Artikel-Nr.",
        accessorKey: "artikel_nr",
        cell: ({ getValue }) => (
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
            {String(getValue() ?? "")}
          </code>
        ),
      },
      {
        id: "bezeichnung",
        header: "Bezeichnung",
        accessorKey: "bezeichnung",
        cell: ({ getValue }) => (
          <span className="font-medium">{String(getValue() ?? "—")}</span>
        ),
      },
      {
        id: "werkstoff",
        header: "Werkstoff",
        accessorKey: "werkstoff",
        cell: ({ getValue }) => String(getValue() ?? "—"),
      },
      {
        id: "abmessungen",
        header: "Abmessungen",
        accessorKey: "abmessungen",
        cell: ({ getValue }) => String(getValue() ?? "—"),
      },
      {
        id: "einheit",
        header: "ME",
        accessorKey: "einheit",
        cell: ({ getValue }) => (
          <span className="text-xs uppercase text-muted-foreground">
            {String(getValue() ?? "")}
          </span>
        ),
      },
      {
        id: "basispreis_eur",
        header: () => <span className="block text-right">Basispreis</span>,
        accessorKey: "basispreis_eur",
        cell: ({ getValue }) => (
          <span className="block text-right font-mono tabular-nums">
            {formatEur(Number(getValue() ?? 0))}
          </span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-card">
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-surface shadow-[0_1px_0_hsl(var(--border))]">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className={
                  onRowClick
                    ? "cursor-pointer hover:bg-muted/60"
                    : i % 2 === 0
                      ? "bg-surface"
                      : "bg-muted/30"
                }
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="whitespace-nowrap border-b border-border/40 px-3 py-2 align-top text-foreground/90"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
