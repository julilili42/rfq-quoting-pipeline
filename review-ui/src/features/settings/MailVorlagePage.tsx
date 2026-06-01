import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, FileText, Info, Mail, RotateCcw, Sparkles } from "lucide-react";
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

const EMAIL_PLACEHOLDERS = ["Betreff", "Firma", "Absender", "Telefon", "Email", "Datum"];
const FILENAME_PLACEHOLDERS = [
  "Kunde",
  "Datum",
  "Belegnummer",
  "Kundennummer",
];

const WORKFLOW_DEFAULTS = workflowPreferencesSchema.parse({});

export function MailVorlagePage() {
  const { data, isLoading, isError, error } = useSettings();
  const save = useSaveSettings();

  if (isLoading) {
    return (
      <PageContainer>
        <LoadingState label="Lade Vorlagen…" />
      </PageContainer>
    );
  }
  if (isError || !data) {
    return (
      <PageContainer>
        <ErrorState error={error ?? "Vorlagen konnten nicht geladen werden."} />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <header className="mb-6">
        <h1 className="font-display text-3xl font-extrabold leading-tight tracking-tight md:text-4xl">
          Vorlagen<span className="text-brand">.</span>
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Mailtext und Dateinamen festlegen.
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => form.reset(initial), [initial]);

  const isDirty = form.formState.isDirty;

  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const filenameRef = useRef<HTMLInputElement>(null);

  const { ref: subjectRegRef, ...subjectRegProps } = form.register("workflow.email_subject_template");
  const { ref: bodyRegRef, ...bodyRegProps } = form.register("workflow.email_body_template");
  const { ref: filenameRegRef, ...filenameRegProps } = form.register("workflow.final_pdf_filename_template");
  const styleHintProps = form.register("workflow.llm_email_body_style_hint");

  const useLlmBody = form.watch("workflow.use_llm_email_body");
  const styleHint = form.watch("workflow.llm_email_body_style_hint") ?? "";

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
        Telefon: initial?.company?.contact_phone ?? "+49 30 123456",
        Email: initial?.company?.contact_email ?? "angebot@beispiel.de",
        Datum: new Date().toLocaleDateString("de-DE"),
      } as Record<string, string>,
      filename: {
        Kunde: "Musterfirma GmbH",
        Belegnummer: "A-2026-0042",
        Kundennummer: "K-10234",
        Ansprechpartner: "Erika Musterfrau",
        Datum: (() => {
          const d = new Date();
          return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
        })(),
      } as Record<string, string>,
    }),
    [initial?.company?.contact_person, initial?.company?.contact_phone, initial?.company?.contact_email],
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
            useLlmBody={useLlmBody}
            onToggleLlmBody={() =>
              form.setValue("workflow.use_llm_email_body", !useLlmBody, { shouldDirty: true })
            }
            styleHintProps={styleHintProps}
            styleHintLength={styleHint.length}
            onInsertSubject={(t) => insertAt("workflow.email_subject_template", subjectRef, t)}
            onInsertBody={(t) => insertAt("workflow.email_body_template", bodyRef, t)}
            onReset={() => {
              form.setValue("workflow.email_subject_template", WORKFLOW_DEFAULTS.email_subject_template, { shouldDirty: true });
              form.setValue("workflow.email_body_template", WORKFLOW_DEFAULTS.email_body_template, { shouldDirty: true });
              form.setValue("workflow.use_llm_email_body", WORKFLOW_DEFAULTS.use_llm_email_body, { shouldDirty: true });
              form.setValue("workflow.llm_email_body_style_hint", WORKFLOW_DEFAULTS.llm_email_body_style_hint, { shouldDirty: true });
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
          bodyGeneratedByLlm={useLlmBody}
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
  useLlmBody,
  onToggleLlmBody,
  styleHintProps,
  styleHintLength,
  onInsertSubject,
  onInsertBody,
  onReset,
}: {
  subjectProps: React.InputHTMLAttributes<HTMLInputElement> & { ref: (el: HTMLInputElement | null) => void };
  bodyProps: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { ref: (el: HTMLTextAreaElement | null) => void };
  subjectLength: number;
  unknownEmail: string[];
  useLlmBody: boolean;
  onToggleLlmBody: () => void;
  styleHintProps: React.TextareaHTMLAttributes<HTMLTextAreaElement>;
  styleHintLength: number;
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
      <div className="space-y-5">
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

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Nachrichtentext</Label>
            <LlmToggle checked={useLlmBody} onToggle={onToggleLlmBody} />
          </div>

          {useLlmBody ? (
            <LlmStyleHintField
              styleHintProps={styleHintProps}
              styleHintLength={styleHintLength}
            />
          ) : (
            <>
              <textarea
                {...bodyProps}
                rows={7}
                placeholder={"Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihre Anfrage…"}
                className="flex w-full resize-y rounded-md border border-input bg-surface px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 min-h-[120px]"
              />
              <PlaceholderChips placeholders={EMAIL_PLACEHOLDERS} onInsert={onInsertBody} />
            </>
          )}
        </div>

        {!useLlmBody && unknownEmail.length > 0 && (
          <UnknownPlaceholderWarning placeholders={unknownEmail} />
        )}
      </div>
    </SectionCard>
  );
}

function LlmToggle({
  checked,
  onToggle,
}: {
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label="KI-Begleittext aktivieren"
      onClick={onToggle}
      className={cn(
        "group inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
        checked
          ? "bg-ek-blue-soft text-ek-blue"
          : "bg-surface-sunk text-muted-foreground hover:text-foreground",
      )}
    >
      <Sparkles className={cn("h-3 w-3", checked && "text-ek-blue")} />
      <span>KI-Begleittext</span>
      <span
        aria-hidden="true"
        className={cn(
          "relative inline-block h-3.5 w-6 rounded-full transition-colors",
          checked ? "bg-ek-blue" : "bg-border",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 h-2.5 w-2.5 rounded-full bg-white shadow-sm transition-transform",
            checked && "translate-x-2.5",
          )}
        />
      </span>
    </button>
  );
}

function LlmStyleHintField({
  styleHintProps,
  styleHintLength,
}: {
  styleHintProps: React.TextareaHTMLAttributes<HTMLTextAreaElement>;
  styleHintLength: number;
}) {
  return (
    <div className="rounded-md border border-ek-blue/20 bg-ek-blue-soft/30 p-3 space-y-2">
      <p className="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
        <Info className="mt-0.5 h-3 w-3 shrink-0" />
        Text wird beim Senden für jede Anfrage individuell generiert (Deutsch oder Englisch).
      </p>
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <Label className="text-[11px] text-muted-foreground">Stil-Hinweis (optional)</Label>
          <span
            className={cn(
              "text-[11px] tabular-nums",
              styleHintLength > 280 ? "font-medium text-warning" : "text-muted-foreground",
            )}
          >
            {styleHintLength}/280
          </span>
        </div>
        <textarea
          {...styleHintProps}
          rows={2}
          maxLength={280}
          placeholder='z.B. "formell, kurz, kein Marketing-Wording"'
          className="flex w-full resize-y rounded-md border border-input bg-surface px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        />
      </div>
    </div>
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
  from, to, subject, body, filename, bodyGeneratedByLlm,
}: {
  from: string;
  to: string;
  subject: string;
  body: string;
  filename: string;
  bodyGeneratedByLlm: boolean;
}) {
  const previewBody = bodyGeneratedByLlm
    ? "[Beispieltext wird beim Senden für jede Anfrage neu generiert.]"
    : body;
  return (
    <div className="xl:sticky xl:top-6 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Vorschau</p>
        <Pill tone="neutral" className="text-[10px]">
          {bodyGeneratedByLlm ? (
            <>
              <Sparkles className="mr-1 h-3 w-3" /> KI-Begleittext
            </>
          ) : (
            "Beispieldaten"
          )}
        </Pill>
      </div>
      <EmailPreview from={from} to={to} subject={subject} body={previewBody} />
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
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-ek-blue-soft text-ek-blue">
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
