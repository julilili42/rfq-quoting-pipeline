import type { MailTemplateSettings } from "../api/reviewApi";
import type { CreateReviewResponse } from "../types";
import { withCacheBust } from "../utils";

declare const Office: any;

type DraftMailContext = {
  subject: string;
  kundenFirma?: string;
  recipientEmail?: string;
  overrideFilename?: string;
};

function resolvePlaceholders(
  template: string,
  vars: Record<string, string>,
): string {
  let result = template;
  for (const [key, value] of Object.entries(vars)) {
    result = result.replaceAll(`[${key}]`, value);
  }
  return result;
}

function plainTextToHtml(text: string): string {
  const normalized = text
    .replaceAll("\\r\\n", "\n")
    .replaceAll("\\n", "\n")
    .replaceAll("\\t", "\t");
  if (/<[a-z][\s\S]*>/i.test(normalized)) return normalized;
  return normalized
    .split("\n\n")
    .map(para => `<p>${para.split("\n").join("<br/>")}</p>`)
    .join("");
}

export async function createDraftMail(
  result: CreateReviewResponse,
  mail: DraftMailContext,
  setStatus: (s: string) => void,
  templates?: MailTemplateSettings,
) {
  const today = new Date().toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  const placeholders: Record<string, string> = {
    Betreff: mail.subject,
    Firma: mail.kundenFirma ?? "",
    Absender: templates?.company_name ?? "",
    Datum: today,
  };

  const subjectTemplate =
    templates?.email_subject_template ?? "Angebot zu Ihrer Anfrage: [Betreff]";
  const bodyTemplate =
    templates?.email_body_template ??
    "<p>Sehr geehrte Damen und Herren,</p><p>vielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot.</p><p>Mit freundlichen Grüßen<br/>[Absender]</p>";

  const subject = resolvePlaceholders(subjectTemplate, placeholders);
  const htmlBody = plainTextToHtml(resolvePlaceholders(bodyTemplate, placeholders));

  const finalPdfUrl =
    result.final_pdf_url ??
    result.draft_pdf_url.replace("/pdf/draft", "/pdf/final");

  const finalPdfFilename =
    mail.overrideFilename ??
    result.final_pdf_filename ??
    result.draft_pdf_filename.replace("Draft_", "").replace("_DRAFT", "_FINAL");

  Office.context.mailbox.displayNewMessageForm({
    toRecipients: mail.recipientEmail ? [mail.recipientEmail] : [],
    subject,
    htmlBody,
    attachments: [
      {
        type: "file",
        name: finalPdfFilename,
        url: withCacheBust(finalPdfUrl),
      },
    ],
  });
  setStatus(`Angebotsmail mit aktueller PDF geöffnet (${result.review_id})`);
}

export function openUrl(url: string) {
  if (Office.context?.ui?.openBrowserWindow) {
    Office.context.ui.openBrowserWindow(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
