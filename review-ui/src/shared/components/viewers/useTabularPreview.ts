import { useQuery } from "@tanstack/react-query";
import Papa from "papaparse";

import { env } from "@/shared/lib/env";

/**
 * Robust CSV/TSV/XLSX → rows loader.
 *
 * Mirrors the parsing strategy in `quoting/ui/review_ui/document_view._read_csv_robust`:
 * try multiple separators, pick the one that yields the most columns. For
 * XLSX we use `xlsx` (SheetJS) to read the first sheet only — that's
 * what the Streamlit version does too.
 */

export interface TabularData {
  columns: string[];
  rows: Record<string, unknown>[];
  totalRows: number;
  truncated: boolean;
}

const MAX_PREVIEW_ROWS = 500;

const SEPARATORS = [";", ",", "\t", "|"];

async function loadTabular(reviewId: string, fileName: string): Promise<TabularData> {
  const url = `${env.apiBaseUrl}/api/reviews/${encodeURIComponent(reviewId)}/attachment/${encodeURIComponent(fileName)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Original konnte nicht geladen werden (${response.status})`);
  }

  const ext = fileName.toLowerCase().split(".").pop();

  if (ext === "xlsx" || ext === "xls") {
    const buffer = await response.arrayBuffer();
    return parseXlsx(buffer);
  }

  const text = await response.text();
  return parseCsv(text, ext === "tsv");
}

function parseCsv(text: string, isTsv: boolean): TabularData {
  const seps = isTsv ? ["\t"] : SEPARATORS;
  let best: TabularData | null = null;

  for (const sep of seps) {
    try {
      const result = Papa.parse<Record<string, unknown>>(text, {
        header: true,
        skipEmptyLines: true,
        delimiter: sep,
        // PapaParse fills empty fields with `""` so we can keep types simple.
      });
      const cols = result.meta.fields ?? [];
      if (cols.length > (best?.columns.length ?? 0)) {
        best = {
          columns: cols,
          rows: result.data.slice(0, MAX_PREVIEW_ROWS),
          totalRows: result.data.length,
          truncated: result.data.length > MAX_PREVIEW_ROWS,
        };
      }
    } catch {
      /* try next separator */
    }
  }

  if (!best) {
    throw new Error("CSV konnte mit keinem Trennzeichen gelesen werden.");
  }
  return best;
}

async function parseXlsx(buffer: ArrayBuffer): Promise<TabularData> {
  // Lazy import — xlsx is ~700KB unminified, no point loading it on
  // every page even if no XLSX is open.
  const XLSX = await import("xlsx");
  const workbook = XLSX.read(buffer, { type: "array" });
  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    return { columns: [], rows: [], totalRows: 0, truncated: false };
  }
  const sheet = workbook.Sheets[sheetName];
  const json = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, {
    defval: "",
  });
  const cols = json.length > 0 ? Object.keys(json[0]) : [];
  return {
    columns: cols,
    rows: json.slice(0, MAX_PREVIEW_ROWS),
    totalRows: json.length,
    truncated: json.length > MAX_PREVIEW_ROWS,
  };
}

export function useTabularPreview(
  reviewId: string,
  fileName: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["original-tabular", reviewId, fileName],
    queryFn: () => loadTabular(reviewId, fileName),
    enabled,
    staleTime: 5 * 60_000,
  });
}
