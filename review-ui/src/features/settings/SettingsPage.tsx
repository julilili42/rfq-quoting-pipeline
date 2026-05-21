import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUpRight, Building2, Settings2 } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { SaveBar } from "@/shared/components/forms/SaveBar";
import { cn } from "@/shared/lib/cn";
import { appSettingsSchema, type AppSettings } from "@/shared/schemas/settings";

import { useSaveSettings, useSettings } from "./hooks/useSettings";

export function SettingsPage() {
  const { data, isLoading, isError, error } = useSettings();
  const save = useSaveSettings();

  if (isLoading) {
    return (
      <PageContainer>
        <LoadingState label="Lade Einstellungen…" />
      </PageContainer>
    );
  }
  if (isError || !data) {
    return (
      <PageContainer>
        <ErrorState error={error ?? "Einstellungen konnten nicht geladen werden."} />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <header className="mb-10">
        <h1 className="font-display text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
          Einstellungen<span className="text-brand">.</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Stammdaten für PDF-Header, Editor-Verhalten und Matching-Schwellen.
        </p>
      </header>

      <SettingsForm
        initial={data}
        onSave={(s) => save.mutate(s)}
        saving={save.isPending}
        saveSuccess={save.isSuccess}
        saveError={save.isError ? save.error : null}
      />
    </PageContainer>
  );
}

interface SettingsFormProps {
  initial: AppSettings;
  saving: boolean;
  saveSuccess: boolean;
  saveError: unknown;
  onSave: (settings: AppSettings) => void;
}

function SettingsForm({ initial, saving, saveSuccess, saveError, onSave }: SettingsFormProps) {
  const form = useForm<AppSettings>({
    resolver: zodResolver(appSettingsSchema),
    defaultValues: initial,
  });

  useEffect(() => form.reset(initial), [initial, form]);

  const isDirty = form.formState.isDirty;

  return (
    <form
      className="space-y-6"
      onSubmit={form.handleSubmit((values: AppSettings) => onSave(values))}
    >
      <SettingsCard
        icon={<Building2 className="h-4 w-4" />}
        title="Unternehmen"
        description="Daten für PDF-Header und Kontakt-Footer."
      >
        <SubSection title="Firmendaten">
          <Grid>
            <Field label="Firmenname">
              <Input placeholder="Muster GmbH" {...form.register("company.company_name")} />
            </Field>
            <Field label="Land">
              <Input placeholder="Deutschland" {...form.register("company.company_country")} />
            </Field>
          </Grid>
          <Field label="Anschrift">
            <div className="space-y-2">
              <Input
                placeholder="Musterstraße 1"
                {...form.register("company.company_address")}
              />
              <Input
                placeholder="12345 Musterstadt"
                {...form.register("company.company_zip_city")}
              />
            </div>
          </Field>
        </SubSection>

        <SubSection title="Kontakt">
          <Grid>
            <Field label="Name">
              <Input placeholder="Max Mustermann" {...form.register("company.contact_person")} />
            </Field>
            <Field label="Telefon">
              <Input placeholder="+49 30 123456" {...form.register("company.contact_phone")} />
            </Field>
            <Field label="E-Mail">
              <Input
                type="email"
                placeholder="angebot@muster.de"
                {...form.register("company.contact_email")}
              />
            </Field>
            <Field label="Gültigkeit" hint="Tage">
              <Input
                type="number"
                min={1}
                max={365}
                {...form.register("company.validity_days", { valueAsNumber: true })}
              />
            </Field>
          </Grid>
        </SubSection>

        <SubSection title="Kommerzielle Standards">
          <Grid>
            <Field label="Lieferbedingung">
              <Input placeholder="EXW Werk" {...form.register("company.delivery_term")} />
            </Field>
            <Field label="Zahlungsbedingung">
              <Input placeholder="30 Tage netto" {...form.register("company.payment_term")} />
            </Field>
          </Grid>
        </SubSection>
      </SettingsCard>

      <SettingsCard
        icon={<Settings2 className="h-4 w-4" />}
        title="Verarbeitung"
        description="Matching-Schwellen und Editor-Verhalten."
      >
        <SubSection title="Matching">
          <Grid>
            <Field label="Fuzzy-Schwelle" hint="50 – 100">
              <Input
                type="number"
                min={50}
                max={100}
                {...form.register("matching.fuzzy_threshold", { valueAsNumber: true })}
              />
            </Field>
            <Field label="Semantische Schwelle" hint="40 – 100">
              <Input
                type="number"
                min={40}
                max={100}
                {...form.register("matching.semantic_threshold", { valueAsNumber: true })}
              />
            </Field>
          </Grid>
        </SubSection>

        <SubSection title="Editor-Verhalten">
          <div className="divide-y divide-border">
            <Toggle
              label="PDF automatisch neu generieren"
              checked={form.watch("workflow.auto_refresh_pdf")}
              onCheckedChange={(v) =>
                form.setValue("workflow.auto_refresh_pdf", v, { shouldDirty: true })
              }
            />
            <Toggle
              label="Reset bestätigen"
              checked={form.watch("workflow.confirm_before_reset")}
              onCheckedChange={(v) =>
                form.setValue("workflow.confirm_before_reset", v, { shouldDirty: true })
              }
            />
          </div>
        </SubSection>
      </SettingsCard>

      <div className="pt-2">
        <Link
          to="/debug"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          System-Diagnose
          <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>

      <SaveBar isDirty={isDirty} saving={saving} saveSuccess={saveSuccess} saveError={saveError} />
    </form>
  );
}

function SettingsCard({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-5">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-soft text-brand">
            {icon}
          </span>
          <div>
            <CardTitle className="text-base">{title}</CardTitle>
            {description && (
              <CardDescription className="mt-0.5 text-xs">{description}</CardDescription>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">{children}</CardContent>
    </Card>
  );
}

function SubSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-4 border-t border-border pt-6 first:border-t-0 first:pt-0">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">{children}</div>;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">
        {label}
        {hint && <span className="ml-1 font-normal text-muted-foreground">· {hint}</span>}
      </Label>
      {children}
    </div>
  );
}

function Toggle({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-3.5 first:pt-0 last:pb-0">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-label={label}
        aria-checked={checked}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          checked ? "bg-brand" : "bg-muted",
        )}
      >
        <span
          className={cn(
            "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-md transition-transform",
            checked ? "translate-x-4" : "translate-x-0",
          )}
        />
      </button>
    </div>
  );
}
