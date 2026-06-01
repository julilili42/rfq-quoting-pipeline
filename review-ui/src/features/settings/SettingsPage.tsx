import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowUpRight, Building2, Settings2 } from "lucide-react";
import React, { useEffect, type ReactNode } from "react";
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
      <header className="mb-6">
        <h1 className="font-display text-3xl font-extrabold leading-tight tracking-tight md:text-4xl">
          Einstellungen<span className="text-brand">.</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Workflow, PDF-Ausgabe und Matching steuern.
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => form.reset(initial), [initial]);

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
              <SettingsInput placeholder="Muster GmbH" {...form.register("company.company_name")} />
            </Field>
            <Field label="Land">
              <SettingsInput placeholder="Deutschland" {...form.register("company.company_country")} />
            </Field>
            <Field label="Straße">
              <SettingsInput
                placeholder="Musterstraße 1"
                {...form.register("company.company_address")}
              />
            </Field>
            <Field label="PLZ / Ort">
              <SettingsInput
                placeholder="12345 Musterstadt"
                {...form.register("company.company_zip_city")}
              />
            </Field>
          </Grid>
        </SubSection>

        <SubSection title="Kontakt">
          <Grid>
            <Field label="Name">
              <SettingsInput placeholder="Max Mustermann" {...form.register("company.contact_person")} />
            </Field>
            <Field label="Telefon">
              <SettingsInput placeholder="+49 30 123456" {...form.register("company.contact_phone")} />
            </Field>
            <Field label="E-Mail">
              <SettingsInput
                type="email"
                placeholder="angebot@muster.de"
                {...form.register("company.contact_email")}
              />
            </Field>
            <Field label="Gültigkeit" hint="Tage">
              <SettingsInput
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
              <SettingsInput placeholder="EXW Werk" {...form.register("company.delivery_term")} />
            </Field>
            <Field label="Zahlungsbedingung">
              <SettingsInput placeholder="30 Tage netto" {...form.register("company.payment_term")} />
            </Field>
          </Grid>
        </SubSection>
      </SettingsCard>

        <SettingsCard
          icon={<Settings2 className="h-4 w-4" />}
          title="Verarbeitung"
          description="Schwellen für automatische Stammdaten-Treffer."
        >
        <SubSection title="Matching">
          <Grid>
            <Field label="Fuzzy-Schwelle" hint="50 – 100">
              <SettingsInput
                type="number"
                min={50}
                max={100}
                {...form.register("matching.fuzzy_threshold", { valueAsNumber: true })}
              />
            </Field>
            <Field label="Semantische Schwelle" hint="40 – 100">
              <SettingsInput
                type="number"
                min={40}
                max={100}
                {...form.register("matching.semantic_threshold", { valueAsNumber: true })}
              />
            </Field>
          </Grid>
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
      <CardHeader className="p-5">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-ek-blue-soft text-ek-blue">
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
      <CardContent className="space-y-4 px-5 pb-5">{children}</CardContent>
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
    <section className="space-y-3 border-t border-border pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-5 gap-y-3 md:grid-cols-2">{children}</div>;
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
    <div className="space-y-1">
      <Label className="text-xs">
        {label}
        {hint && <span className="ml-1 font-normal text-muted-foreground">· {hint}</span>}
      </Label>
      {children}
    </div>
  );
}

const SettingsInput = React.forwardRef<HTMLInputElement, React.ComponentProps<typeof Input>>(
  ({ className, ...props }, ref) => <Input ref={ref} className={cn("h-9", className)} {...props} />,
);
SettingsInput.displayName = "SettingsInput";
