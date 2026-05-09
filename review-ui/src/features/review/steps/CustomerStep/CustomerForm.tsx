import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useHotkeys } from "react-hotkeys-hook";

import { FormField } from "@/shared/components/ui/FormField";
import { Input } from "@/shared/components/ui/input";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import type { Anfrage, Evidence } from "@/shared/schemas/anfrage";
import { Button } from "@/shared/components/ui/button";

import { useSaveAndRegenerate } from "../../hooks/useReviewMutations";
import { customerFormSchema, type CustomerFormValues } from "./schemas";

interface CustomerFormProps {
  reviewId: string;
  anfrage: Anfrage;
  onEvidenceSelect?: (ev: Evidence) => void;
}

/**
 * Customer header + commercial terms form.
 *
 * Edits are committed on **blur** rather than on every keystroke —
 * a price/PDF rebuild is expensive enough that per-keystroke commits
 * would make the UI feel sluggish. react-hook-form takes care of
 * controlled input wiring; the actual save delegates to the same
 * `saveAndRegenerate` mutation as the positions step.
 */
export function CustomerForm({ reviewId, anfrage, onEvidenceSelect }: CustomerFormProps) {
  const trackChange = useReviewUiStore((s) => s.trackChange);
  const saveAndRegenerate = useSaveAndRegenerate(reviewId);

  const form = useForm<CustomerFormValues>({
    resolver: zodResolver(customerFormSchema),
    defaultValues: pickCustomerFields(anfrage),
  });

  // Keep form values in sync with upstream changes (e.g. another step
  // saved Anfrage edits and we re-rendered from a fresh detail).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { form.reset(pickCustomerFields(anfrage)); }, [anfrage]);

  const commitField = (field: keyof CustomerFormValues) => {
    const fieldPath = field;
    trackChange(fieldPath);

    const next: Anfrage = {
      ...anfrage,
      ...form.getValues(),
    };
    if (
      JSON.stringify(pickCustomerFields(next)) ===
      JSON.stringify(pickCustomerFields(anfrage))
    ) {
      return; // nothing changed
    }
    saveAndRegenerate.mutate({ anfrage: next });
  };

  const fillToday = () => {
  const today = new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date());

  form.setValue("datum", today, { shouldDirty: true });
  trackChange("datum");

  const next: Anfrage = {
    ...anfrage,
    ...form.getValues(),
    datum: today,
  };

  saveAndRegenerate.mutate({ anfrage: next });
};

  useHotkeys("alt+h", fillToday, {
    enabled: !saveAndRegenerate.isPending,
    preventDefault: true,
  });

  return (
    <section className="space-y-6">
      <div>
        <h2 className="section-label mb-2">Kundendaten prüfen</h2>
        {saveAndRegenerate.isPending && (
          <span className="text-xs font-semibold text-info">
            PDF wird neu berechnet…
          </span>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface p-5 shadow-card">
        <h3 className="mb-4 font-display text-base font-bold tracking-tight">
          Kunde &amp; Anfrage-Header
        </h3>
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
          <FormField label="Firma" evidence={anfrage.header_evidence?.kunde_firma} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("kunde_firma")}
              onBlur={() => commitField("kunde_firma")}
              placeholder="z. B. Musterfirma GmbH"
            />
          </FormField>
          <FormField label="Ansprechpartner" evidence={anfrage.header_evidence?.kunde_ansprechpartner} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("kunde_ansprechpartner")}
              onBlur={() => commitField("kunde_ansprechpartner")}
              placeholder="z. B. Frau Müller"
            />
          </FormField>
          <FormField label="E-Mail" evidence={anfrage.header_evidence?.kunde_email} onNavigate={onEvidenceSelect}>
            <Input
              type="email"
              {...form.register("kunde_email")}
              onBlur={() => commitField("kunde_email")}
              placeholder="kontakt@firma.de"
            />
          </FormField>
          <FormField label="Kunden-Nr." evidence={anfrage.header_evidence?.kundennummer} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("kundennummer")}
              onBlur={() => commitField("kundennummer")}
              placeholder="z. B. 1234"
            />
          </FormField>
          <FormField label="Anfrage / Beleg-Nr." evidence={anfrage.header_evidence?.belegnummer} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("belegnummer")}
              onBlur={() => commitField("belegnummer")}
              placeholder="z. B. ANF-2024-001"
            />
          </FormField>
          <FormField label="Datum" evidence={anfrage.header_evidence?.datum} onNavigate={onEvidenceSelect}>
            <div className="flex gap-2">
              <Input
                {...form.register("datum")}
                onBlur={() => commitField("datum")}
                placeholder="z. B. 15.03.2024"
              />
              <div className="group relative">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={fillToday}
                  disabled={saveAndRegenerate.isPending}
                >
                  Heute
                </Button>
                <ShortcutHint keys={["Alt", "H"]} />
              </div>
            </div>
          </FormField>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5 shadow-card">
        <h3 className="mb-4 font-display text-base font-bold tracking-tight">
          Kommerzielle Bedingungen
        </h3>
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
          <FormField label="Lieferbedingung / Incoterms" evidence={anfrage.header_evidence?.incoterms} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("incoterms")}
              onBlur={() => commitField("incoterms")}
              placeholder="z. B. EXW Werk"
            />
          </FormField>
          <FormField label="Zahlungsbedingung" evidence={anfrage.header_evidence?.zahlungsbedingungen} onNavigate={onEvidenceSelect}>
            <Input
              {...form.register("zahlungsbedingungen")}
              onBlur={() => commitField("zahlungsbedingungen")}
              placeholder="z. B. 30 Tage netto"
            />
          </FormField>
        </div>
      </div>
    </section>
  );
}

function pickCustomerFields(a: Anfrage): CustomerFormValues {
  return {
    kunde_firma: a.kunde_firma ?? "",
    kunde_ansprechpartner: a.kunde_ansprechpartner ?? "",
    kunde_email: a.kunde_email ?? "",
    kundennummer: a.kundennummer ?? "",
    belegnummer: a.belegnummer ?? "",
    datum: a.datum ?? "",
    incoterms: a.incoterms ?? "",
    zahlungsbedingungen: a.zahlungsbedingungen ?? "",
  };
}

