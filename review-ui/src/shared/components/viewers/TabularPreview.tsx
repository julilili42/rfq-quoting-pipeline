import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo } from "react";

import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";

import { useTabularPreview } from "./useTabularPreview";

interface TabularPreviewProps {
  reviewId: string;
  fileName: string;
}

/**
 * In-browser CSV/TSV/XLSX preview.
 *
 * Replaces the old "kein Inline-Preview" dead-end with a real table.
 * Capped at the first 500 rows so multi-MB exports don't blow up the
 * DOM — the user can still download the file via the toolbar above.
 */
export function TabularPreview({ reviewId, fileName }: TabularPreviewProps) {
  const { data, isLoading, isError, error } = useTabularPreview(
    reviewId,
    fileName,
  );

  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      (data?.columns ?? []).map((col) => ({
        id: col,
        accessorKey: col,
        header: () => col || "—",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined || v === "") return "—";
          return String(v);
        },
      })),
    [data?.columns],
  );

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return <LoadingState label="Lade Tabelle…" className="py-16" />;
  }
  if (isError) {
    return <ErrorState error={error} />;
  }
  if (!data || data.rows.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-muted-foreground">
        Tabelle ist leer.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-muted px-4 py-2 text-xs text-muted-foreground">
        <span>
          <strong className="text-foreground">{data.totalRows}</strong>{" "}
          {data.totalRows === 1 ? "Zeile" : "Zeilen"}
          {" · "}
          <strong className="text-foreground">{data.columns.length}</strong>{" "}
          {data.columns.length === 1 ? "Spalte" : "Spalten"}
        </span>
        {data.truncated && (
          <span className="text-warning">
            Vorschau auf {data.rows.length} Zeilen begrenzt
          </span>
        )}
      </div>

      <div className="max-h-[680px] overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-surface shadow-[0_1px_0_hsl(var(--border))]">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="border-b border-border px-3 py-2 text-left font-semibold text-foreground"
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
                className={i % 2 === 0 ? "bg-surface" : "bg-muted/30"}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="whitespace-nowrap border-b border-border/40 px-3 py-1.5 text-foreground/90"
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
