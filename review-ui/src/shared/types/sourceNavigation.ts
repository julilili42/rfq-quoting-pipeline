import type { Evidence } from "@/shared/schemas/anfrage";

export type SourceTargetKind = "position" | "header" | "generic";

export interface SourceNavigationTarget {
  evidence: Evidence;
  targetKind: SourceTargetKind;
  candidates: string[];
  label?: string;
}

export function genericSourceTarget(evidence: Evidence): SourceNavigationTarget {
  return {
    evidence,
    targetKind: "generic",
    candidates: [],
  };
}
