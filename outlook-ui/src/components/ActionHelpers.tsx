import type { ReactNode } from "react";

export function SecondaryActions({ children }: { children: ReactNode }) {
  return <div className="secondary-actions">{children}</div>;
}
