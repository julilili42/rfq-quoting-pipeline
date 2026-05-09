import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, FileText, Mail, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
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
import { Pill } from "@/shared/components/ui/pill";
import { ErrorState } from "@/shared/components/feedback/ErrorState";
import { LoadingState } from "@/shared/components/feedback/LoadingState";
import { PageContainer } from "@/shared/components/layout/PageContainer";
import { SaveBar } from "@/shared/components/forms/SaveBar";
import { cn } from "@/shared/lib/cn";
import {
  appSettingsSchema,
  workflowPreferencesSchema,
  type AppSettings,
} from "@/shared/schemas/settings";

import { EmailPreview } from "./components/EmailPreview";
import { PlaceholderChips } from "./components/PlaceholderChips";
import { useSaveSettings, useSettings } from "./hooks/useSettings";
import {
  findUnknownPlaceholders,
  resolvePlaceholders,
} from "./utils/resolvePlaceholders";

const EMAIL_PLACEHOLDERS = ["Betreff", "Firma", "Absender", "Datum"];
const FILENAME_PLACEHOLDERS = [
  "Kunde",
  "Datum",
  "Belegnummer",
  "Kundennummer",
  "Vorgangsnummer",
];

const WORKFLOW_DEFAULTS = workflowPreferencesSchema.parse({});

export function MailVorlagePage() {
  const { data, isLoading, isError, error } = useSettings();
  const save = useSaveSettings();

  if (isLoading) {
    return (
      <PageContainer wide>
        <LoadingState label="Lade Vorlagen…" />
      </PageContainer>
    );
  }
  if (isError || !data) {
    return (
      <PageContainer wide>
        <ErrorState error={error ?? "Vorlagen konnten nicht geladen werden."} />
      </PageContainer>
    );
  }

  return (
    <PageContainer wide>
      <header className="mb-8">
        <h1 className="font-display text-4xl font-extrabold tracking-tight md:text-5xl">
          E-Mail & Dateiname<span className="text-brand">.</span>
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Vorlage für ausgehende Angebotsmail und Name der finalen PDF.
        </p>
      </header>

      <MailVorlageForm
        initial={data}
        onSave={(s) => save.mutate(s)}
        saving={save.isPending}
        saveSuccess={save.isSuccess}
        saveError={save.isError ? save.error : null}
      />
    </PageContainer>
  );
}

interface FormProps {
  initial: AppSettings;
  saving: boolean;
  saveSuccess: boolean;
  saveError: unknown;
  onSave: (settings: AppSettings) => void;
}

function MailVorlageForm({ initial, saving, saveSuccess, saveError, onSave }: FormProps) {
  const form = useForm<AppSettings>({
    resolver: zodResolver(appSettingsSchema),
    defaultValues: initial,
  });

  useEffect(() => form.reset(initial), [initial, form]);

  const isDirty = form.formState.isDirty;

  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const filenameRef = useRef<HTMLInputElement>(null);

  const { ref: subjectRegRef, ...subjectRegProps } = form.register("workflow.email_subject_template");
  const { ref: bodyRegRef, ...bodyRegProps } = form.register("workflow.email_body_template");
  const { ref: filenameRegRef, ...filenameRegProps } = form.register("workflow.final_pdf_filename_template");

  function insertAt(
    fieldPath: "workflow.email_subject_template" | "workflow.email_body_template" | "workflow.final_pdf_filename_template",
    ref: React.RefObject<HTMLInputElement | HTMLTextAreaElement>,
    text: string,
  ) {
    const el = ref.current;
    const current = (form.getValues(fieldPath) as string) ?? "";
    const start = el?.selectionStart ?? current.length;
    const end = el?.selectionEnd ?? current.length;
    const newValue = current.slice(0, start) + text + current.slice(end);
    form.setValue(fieldPath, newValue, { shouldDirty: true });
    if (el) {
      requestAnimationFrame(() => {
        el.focus();
        const pos = start + text.length;
        el.setSelectionRange(pos, pos);
      });
    }
  }

  const [subject, body, filename] = form.watch([
    "workflow.email_subject_template",
    "workflow.email_body_template",
    "workflow.final_pdf_filename_template",
  ]);

  const sampleData = useMemo(
    () => ({
      email: {
        Betreff: "Anfrage Hydraulikpumpe XL-200",
        Firma: "Musterfirma GmbH",
        Absender: initial?.company?.contact_person ?? "Max Mustermann",
        Datum: new Date().toLocaleDateString("de-DE"),
      } as Record<string, string>,
      filename: {
        Kunde: "Musterfirma GmbH",
        Belegnummer: "A-2026-0042",
        Kundennummer: "K-10234",
        Vorgangsnummer: "V-5501",
        Ansprechpartner: "Erika Musterfrau",
        Datum: (() => {
          const d = new Date();
          return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
        })(),
      } as Record<string, string>,
    }),
    [initial?.company?.contact_person],
  );

  const previewSubject = resolvePlaceholders(subject ?? "", sampleData.email);
  const previewBody = resolvePlaceholders(body ?? "", sampleData.email);
  const previewFilename = resolvePlaceholders(filename ?? "", sampleData.filename).replace(/ /g, "_");

  const unknownEmail = [
    ...findUnknownPlaceholders(subject ?? "", EMAIL_PLACEHOLDERS),
    ...findUnknownPlaceholders(body ?? "", EMAIL_PLACEHOLDERS),
  ].filter((v, i, a) => a.indexOf(v) === i);

  const unknownFilename = findUnknownPlaceholders(filename ?? "", FILENAME_PLACEHOLDERS);

  // Merge react-hook-form refs with local cursor-tracking refs
  const mergedSubjectRef = (el: HTMLInputElement | null) => {
    subjectRegRef(el);
    (subjectRef as React.MutableRefObject<HTMLInputElement | null>).current = el;
  };
  const mergedBodyRef = (el: HTMLTextAreaElement | null) => {
    bodyRegRef(el);
    (bodyRef as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
  };
  const mergedFilenameRef = (el: HTMLInputElement | null) => {
    filenameRegRef(el);
    (filenameRef as React.MutableRefObject<HTMLInputElement | null>).current = el;
  };

  return (
    <form
      className="space-y-6"
      onSubmit={form.handleSubmit((values: AppSettings) => onSave(values))}
    >
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2 xl:items-start">
        <div className="space-y-5">
          <EmailTemplateSection
            subjectProps={{ ...subjectRegProps, ref: mergedSubjectRef }}
            bodyProps={{ ...bodyRegProps, ref: mergedBodyRef }}
            subjectLength={(subject ?? "").length}
            unknownEmail={unknownEmail}
            onInsertSubject={(t) => insertAt("workflow.email_subject_template", subjectRef, t)}
            onInsertBody={(t) => insertAt("workflow.email_body_template", bodyRef, t)}
            onReset={() => {
              form.setValue("workflow.email_subject_template", WORKFLOW_DEFAULTS.email_subject_template, { shouldDirty: true });
              form.setValue("workflow.email_body_template", WORKFLOW_DEFAULTS.email_body_template, { shouldDirty: true });
            }}
          />
          <FilenameTemplateSection
            filenameProps={{ ...filenameRegProps, ref: mergedFilenameRef }}
            unknownFilename={unknownFilename}
            onInsertFilename={(t) => insertAt("workflow.final_pdf_filename_template", filenameRef, t)}
            onReset={() => form.setValue("workflow.final_pdf_filename_template", WORKFLOW_DEFAULTS.final_pdf_filename_template, { shouldDirty: true })}
          />
        </div>
        <TemplatePreviewPanel
          from={initial?.company?.company_name || initial?.company?.contact_person || "Ihre Firma"}
          to={sampleData.email["Firma"]}
          subject={previewSubject}
          body={previewBody}
          filename={previewFilename}
        />
      </div>
      <SaveBar isDirty={isDirty} saving={saving} saveSuccess={saveSuccess} saveError={saveError} />
    </form>
  );
}

function EmailTemplateSection({
  subjectProps,
  bodyProps,
  subjectLength,
  unknownEmail,
  onInsertSubject,
  onInsertBody,
  onReset,
}: {
  subjectProps: React.InputHTMLAttributes<HTMLInputElement> & { ref: (el: HTMLInputElement | null) => void };
  bodyProps: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { ref: (el: HTMLTextAreaElement | null) => void };
  subjectLength: number;
  unknownEmail: string[];
  onInsertSubject: (text: string) => void;
  onInsertBody: (text: string) => void;
  onReset: () => void;
}) {
  return (
    <SectionCard
      icon={<Mail className="h-4 w-4" />}
      title="E-Mail Vorlage"
      description="Betreff und Text der Angebotsmail in Outlook"
      onReset={onReset}
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Betreff</Label>
            <span className={cn("text-[11px] tabular-nums", subjectLength > 60 ? "font-medium text-warning" : "text-muted-foreground")}>
              {subjectLength}/60
            </span>
          </div>
          <Input {...subjectProps} placeholder="Angebot zu Ihrer Anfrage: [Betreff]" />
          <PlaceholderChips placeholders={EMAIL_PLACEHOLDERS} onInsert={onInsertSubject} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Nachrichtentext</Label>
          <textarea
            {...bodyProps}
            rows={7}
            placeholder={"Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihre Anfrage…"}
            className="flex w-full resize-y rounded-md border border-input bg-surface px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 min-h-[120px]"
          />
          <PlaceholderChips placeholders={EMAIL_PLACEHOLDERS} onInsert={onInsertBody} />
        </div>
        {unknownEmail.length > 0 && <UnknownPlaceholderWarning placeholders={unknownEmail} />}
      </div>
    </SectionCard>
  );
}

function FilenameTemplateSection({
  filenameProps,
  unknownFilename,
  onInsertFilename,
  onReset,
}: {
  filenameProps: React.InputHTMLAttributes<HTMLInputElement> & { ref: (el: HTMLInputElement | null) => void };
  unknownFilename: string[];
  onInsertFilename: (text: string) => void;
  onReset: () => void;
}) {
  return (
    <SectionCard
      icon={<FileText className="h-4 w-4" />}
      title="Dateiname finale PDF"
      description="Name der PDF-Datei beim Finalisieren eines Angebots"
      onReset={onReset}
    >
      <div className="space-y-1.5">
        <Label className="text-xs">Dateiname-Vorlage</Label>
        <Input {...filenameProps} placeholder="Angebot_[Kunde].pdf" />
        <PlaceholderChips placeholders={FILENAME_PLACEHOLDERS} onInsert={onInsertFilename} />
        {unknownFilename.length > 0 && <UnknownPlaceholderWarning placeholders={unknownFilename} />}
      </div>
    </SectionCard>
  );
}

function TemplatePreviewPanel({
  from, to, subject, body, filename,
}: {
  from: string;
  to: string;
  subject: string;
  body: string;
  filename: string;
}) {
  return (
    <div className="xl:sticky xl:top-6 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Vorschau</p>
        <Pill tone="neutral" className="text-[10px]">Beispieldaten</Pill>
      </div>
      <EmailPreview from={from} to={to} subject={subject} body={body} />
      <div className="rounded-lg border border-border bg-surface px-4 py-3">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Dateiname</p>
        <p className="font-mono text-sm text-foreground break-all">
          {filename || <span className="italic text-muted-foreground">Kein Dateiname</span>}
        </p>
      </div>
    </div>
  );
}

function SectionCard({
  icon,
  title,
  description,
  onReset,
  children,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  onReset: () => void;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-soft text-brand">
              {icon}
            </span>
            <div>
              <CardTitle className="text-sm">{title}</CardTitle>
              {description && (
                <CardDescription className="mt-0.5 text-[11px]">
                  {description}
                </CardDescription>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onReset}
            className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <RotateCcw className="h-3 w-3" />
            Standard
          </button>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function UnknownPlaceholderWarning({ placeholders }: { placeholders: string[] }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-soft px-3 py-2">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
      <p className="text-[11px] text-warning">
        {placeholders.map((p, i) => (
          <span key={p}>
            <code className="font-mono">[{p}]</code>
            {i < placeholders.length - 1 && ", "}
          </span>
        ))}{" "}
        {placeholders.length === 1 ? "wird" : "werden"} nicht ersetzt.
      </p>
    </div>
  );
}
