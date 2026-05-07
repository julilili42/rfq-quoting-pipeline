import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, FileText, Gauge, Mail, Save, Settings2, User } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/shared/components/ui/button";
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
      <header className="mb-8">
        <h1 className="font-display text-4xl font-extrabold tracking-tight md:text-5xl">
          Einstellungen<span className="text-brand">.</span>
        </h1>
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
      className="space-y-5"
      onSubmit={form.handleSubmit((values) => onSave(values))}
    >
      {/* Firmendaten */}
      <SettingsCard
        icon={<Building2 className="h-4 w-4" />}
        title="Firmendaten"
      >
        <Grid>
          <Field label="Firmenname">
            <Input placeholder="Muster GmbH" {...form.register("company.company_name")} />
          </Field>
          <Field label="Land">
            <Input placeholder="Deutschland" {...form.register("company.company_country")} />
          </Field>
          <Field label="Straße & Hausnummer">
            <Input placeholder="Musterstraße 1" {...form.register("company.company_address")} />
          </Field>
          <Field label="PLZ & Ort">
            <Input placeholder="12345 Musterstadt" {...form.register("company.company_zip_city")} />
          </Field>
        </Grid>
      </SettingsCard>

      {/* Kontaktperson */}
      <SettingsCard
        icon={<User className="h-4 w-4" />}
        title="Kontaktperson"
      >
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
          <Field label="Angebotsgültigkeit" hint="Tage">
            <Input
              type="number"
              min={1}
              max={365}
              {...form.register("company.validity_days", { valueAsNumber: true })}
            />
          </Field>
        </Grid>
      </SettingsCard>

      {/* Kommerzielle Standards */}
      <SettingsCard
        icon={<FileText className="h-4 w-4" />}
        title="Kommerzielle Standards"
      >
        <Grid>
          <Field label="Lieferbedingung">
            <Input placeholder="EXW Werk" {...form.register("company.delivery_term")} />
          </Field>
          <Field label="Zahlungsbedingung">
            <Input placeholder="30 Tage netto" {...form.register("company.payment_term")} />
          </Field>
        </Grid>
      </SettingsCard>

      {/* E-Mail Vorlage */}
      <SettingsCard
        icon={<Mail className="h-4 w-4" />}
        title="E-Mail Vorlage"
        description="Betreff und Text der Angebotsmail in Outlook"
      >
        <div className="space-y-4">
          <Field label="Betreff">
            <Input
              placeholder="Angebot zu Ihrer Anfrage: [Betreff]"
              {...form.register("workflow.email_subject_template")}
            />
          </Field>
          <Field label="Nachrichtentext (HTML)">
            <textarea
              rows={5}
              placeholder="<p>Sehr geehrte Damen und Herren,</p>…"
              className="flex w-full rounded-md border border-input bg-surface px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-y min-h-[100px]"
              {...form.register("workflow.email_body_template")}
            />
          </Field>
          <p className="text-[11px] text-muted-foreground">
            Platzhalter: <code className="rounded bg-foreground/5 px-1 font-mono">[Betreff]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Firma]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Absender]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Datum]</code>
          </p>
        </div>
      </SettingsCard>

      {/* Matching */}
      <SettingsCard
        icon={<Gauge className="h-4 w-4" />}
        title="Matching"
      >
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
      </SettingsCard>

      {/* Workflow */}
      <SettingsCard
        icon={<Settings2 className="h-4 w-4" />}
        title="Workflow &amp; PDF"
      >
        <div className="divide-y divide-border">
          <Toggle
            label="PDF automatisch neu generieren"
            checked={form.watch("workflow.auto_refresh_pdf")}
            onCheckedChange={(v) => form.setValue("workflow.auto_refresh_pdf", v, { shouldDirty: true })}
          />
          <Toggle
            label="Reset bestätigen"
            checked={form.watch("workflow.confirm_before_reset")}
            onCheckedChange={(v) => form.setValue("workflow.confirm_before_reset", v, { shouldDirty: true })}
          />
          <div className="py-4">
            <Field label="Standard-Dateiname finale PDF">
              <Input
                placeholder="Angebot_[Kunde].pdf"
                {...form.register("workflow.final_pdf_filename_template")}
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Platzhalter: <code className="rounded bg-foreground/5 px-1 font-mono">[Kunde]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Belegnummer]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Kundennummer]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Vorgangsnummer]</code> · <code className="rounded bg-foreground/5 px-1 font-mono">[Datum]</code>
              </p>
            </Field>
          </div>
        </div>
      </SettingsCard>

      {/* Save bar */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t border-border bg-background/90 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6">
        <div className="flex items-center justify-between gap-4">
          <span className={cn("text-xs text-muted-foreground transition-opacity", isDirty ? "opacity-100" : "opacity-0")}>
            Ungespeicherte Änderungen
          </span>
          <div className="flex items-center gap-3">
            {saveSuccess && !isDirty && (
              <span className="text-xs font-medium text-success">Gespeichert</span>
            )}
            {saveError && (
              <span className="text-xs font-medium text-danger">Speichern fehlgeschlagen</span>
            )}
            <Button variant="primary" type="submit" disabled={saving || !isDirty}>
              <Save className="h-4 w-4" aria-hidden="true" />
              {saving ? "Speichere…" : "Speichern"}
            </Button>
          </div>
        </div>
      </div>
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
      <CardHeader className="pb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-soft text-brand">
            {icon}
          </span>
          <div>
            <CardTitle className="text-sm">{title}</CardTitle>
            {description && <CardDescription className="mt-0.5 text-[11px]">{description}</CardDescription>}
          </div>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
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
        {hint && (
          <span className="ml-1 font-normal text-muted-foreground">· {hint}</span>
        )}
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
    <div className="flex items-center justify-between gap-6 py-3.5">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
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
