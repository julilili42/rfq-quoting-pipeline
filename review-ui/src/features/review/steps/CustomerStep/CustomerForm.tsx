import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarDays } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useHotkeys } from "react-hotkeys-hook";

import { FormField } from "@/shared/components/ui/FormField";
import { Input } from "@/shared/components/ui/input";
import { ShortcutHint } from "@/shared/components/ui/ShortcutHint";
import { useReviewUiStore } from "@/features/review/stores/reviewUiStore";
import { useDelayedVisible } from "@/shared/hooks/useDelayedVisible";
import type { Anfrage, Evidence } from "@/shared/schemas/anfrage";
import { Button } from "@/shared/components/ui/button";
import type { SourceNavigationTarget } from "@/shared/types/sourceNavigation";

import { useSaveAndRegenerate } from "../../hooks/useReviewMutations";
import { ChangedFieldsIndicator } from "../../components/ChangedFieldsIndicator";
import { customerFormSchema, type CustomerFormValues } from "./schemas";

interface CustomerFormProps {
  reviewId: string;
  anfrage: Anfrage;
  onEvidenceSelect?: (target: SourceNavigationTarget) => void;
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
  const refreshChangedFields = useReviewUiStore((s) => s.refreshChangedFields);
  const recordUndoSnapshot = useReviewUiStore((s) => s.recordUndoSnapshot);
  const saveAndRegenerate = useSaveAndRegenerate(reviewId);
  const showSaveStatus = useDelayedVisible(saveAndRegenerate.isPending);

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
    recordUndoSnapshot();
    trackChange(fieldPath);
    refreshChangedFields(next);
    saveAndRegenerate.mutate({ anfrage: next });
  };

  const fillToday = () => {
    const today = new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(new Date());

    recordUndoSnapshot();
    form.setValue("datum", today, { shouldDirty: true });
    trackChange("datum");

    const next: Anfrage = {
      ...anfrage,
      ...form.getValues(),
      datum: today,
    };

    saveAndRegenerate.mutate({ anfrage: next });
    refreshChangedFields(next);
  };

  useHotkeys("alt+h", fillToday, {
    enabled: !saveAndRegenerate.isPending,
    preventDefault: true,
  });

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-label">Kundendaten prüfen</h2>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <ChangedFieldsIndicator />
          {showSaveStatus && (
            <span className="text-xs font-medium text-muted-foreground" role="status">
              Änderungen werden gespeichert…
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5 shadow-card">
        <h3 className="mb-4 font-display text-base font-bold tracking-tight">
          Kunde &amp; Anfrage-Header
        </h3>
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
          <FormField
            label="Firma"
            evidence={anfrage.header_evidence?.kunde_firma}
            sourceTarget={headerSourceTarget(anfrage, "kunde_firma", "Firma")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              {...form.register("kunde_firma")}
              onBlur={() => commitField("kunde_firma")}
              placeholder="z. B. Musterfirma GmbH"
            />
          </FormField>
          <FormField
            label="Ansprechpartner"
            evidence={anfrage.header_evidence?.kunde_ansprechpartner}
            sourceTarget={headerSourceTarget(anfrage, "kunde_ansprechpartner", "Ansprechpartner")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              {...form.register("kunde_ansprechpartner")}
              onBlur={() => commitField("kunde_ansprechpartner")}
              placeholder="z. B. Frau Müller"
            />
          </FormField>
          <FormField
            label="E-Mail"
            evidence={anfrage.header_evidence?.kunde_email}
            sourceTarget={headerSourceTarget(anfrage, "kunde_email", "E-Mail")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              type="email"
              {...form.register("kunde_email")}
              onBlur={() => commitField("kunde_email")}
              placeholder="kontakt@firma.de"
            />
          </FormField>
          <FormField
            label="Kunden-Nr."
            evidence={anfrage.header_evidence?.kundennummer}
            sourceTarget={headerSourceTarget(anfrage, "kundennummer", "Kunden-Nr.")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              {...form.register("kundennummer")}
              onBlur={() => commitField("kundennummer")}
              placeholder="z. B. 1234"
            />
          </FormField>
          <FormField
            label="Anfrage / Beleg-Nr."
            evidence={anfrage.header_evidence?.belegnummer}
            sourceTarget={headerSourceTarget(anfrage, "belegnummer", "Beleg-Nr.")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              {...form.register("belegnummer")}
              onBlur={() => commitField("belegnummer")}
              placeholder="z. B. ANF-2024-001"
            />
          </FormField>
          <FormField
            label="Datum"
            evidence={anfrage.header_evidence?.datum}
            sourceTarget={headerSourceTarget(anfrage, "datum", "Datum")}
            onNavigate={onEvidenceSelect}
            sourceButtonClassName="right-12"
          >
            <div className="flex min-w-0 gap-1.5">
              <Input
                {...form.register("datum")}
                onBlur={() => commitField("datum")}
                placeholder="z. B. 15.03.2024"
                className="min-w-0 flex-1"
              />
              <div className="group relative shrink-0">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={fillToday}
                  disabled={saveAndRegenerate.isPending}
                  aria-label="Datum auf heute setzen"
                  title="Heute"
                  className="h-10 w-10 text-muted-foreground hover:bg-brand-soft hover:text-brand"
                >
                  <CalendarDays className="h-4 w-4" aria-hidden="true" />
                  <span className="sr-only">Heute</span>
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
          <FormField
            label="Lieferbedingung / Incoterms"
            evidence={anfrage.header_evidence?.incoterms}
            sourceTarget={headerSourceTarget(anfrage, "incoterms", "Incoterms")}
            onNavigate={onEvidenceSelect}
          >
            <Input
              {...form.register("incoterms")}
              onBlur={() => commitField("incoterms")}
              placeholder="z. B. EXW Werk"
            />
          </FormField>
          <FormField
            label="Zahlungsbedingung"
            evidence={anfrage.header_evidence?.zahlungsbedingungen}
            sourceTarget={headerSourceTarget(anfrage, "zahlungsbedingungen", "Zahlungsbedingung")}
            onNavigate={onEvidenceSelect}
          >
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

function headerSourceTarget(
  anfrage: Anfrage,
  field: keyof CustomerFormValues,
  label: string,
): SourceNavigationTarget | undefined {
  const evidence = anfrage.header_evidence?.[field] as Evidence | undefined;
  if (!evidence) return undefined;

  const value = anfrage[field];
  const candidates = [
    evidence.source_quote ?? "",
    typeof value === "string" ? value : "",
  ].filter((candidate) => candidate.trim().length > 0);

  return {
    evidence,
    targetKind: "header",
    candidates,
    label,
  };
}
