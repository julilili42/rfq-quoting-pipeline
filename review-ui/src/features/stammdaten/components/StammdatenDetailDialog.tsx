import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { formatEur } from "@/shared/lib/format";
import type { StammdatenRow } from "@/shared/schemas/stammdaten";

interface Props {
  row: StammdatenRow;
  onClose: () => void;
}

export function StammdatenDetailDialog({ row, onClose }: Props) {
  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/20 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-200" />
        <DialogPrimitive.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col border-l border-border bg-surface shadow-xl duration-200 ease-out data-[state=open]:animate-in data-[state=open]:slide-in-from-right-full data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right-full">
          <div className="flex items-start justify-between border-b border-border px-6 py-5">
            <div>
              <DialogPrimitive.Title className="font-mono text-sm font-semibold tracking-tight">
                {row.artikel_nr}
              </DialogPrimitive.Title>
              <p className="mt-1 text-sm text-muted-foreground">{row.bezeichnung}</p>
            </div>
            <DialogPrimitive.Close className="ml-4 mt-0.5 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              <X className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Schließen</span>
            </DialogPrimitive.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            <Section label="Preise">
              <Row label="Basispreis" value={formatEur(row.basispreis_eur)} />
              <Row
                label="Min-Preis (hist.)"
                value={row.preis_min_eur ? formatEur(row.preis_min_eur) : "—"}
              />
              <Row
                label="Max-Preis (hist.)"
                value={row.preis_max_eur ? formatEur(row.preis_max_eur) : "—"}
              />
              <Row label="Angebote (hist.)" value={row.n_offers || "—"} />
            </Section>

            <Section label="Artikel">
              <Row label="Einheit" value={row.einheit} />
              <Row label="Werkstoff" value={row.werkstoff ?? "—"} />
              <Row label="Abmessungen" value={row.abmessungen ?? "—"} />
            </Section>

            <Section label="Klassifizierung">
              <Row label="Sales-Gruppe" value={row.sales_group ?? "—"} />
              <Row label="Material-Gruppe" value={row.material_group ?? "—"} />
            </Section>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </h3>
      <dl className="space-y-2">{children}</dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}
