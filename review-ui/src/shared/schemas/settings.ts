import { z } from "zod";

/**
 * Mirrors `quoting/api/settings_store.py`.
 */

export const companyProfileSchema = z.object({
  company_name: z.string().default(""),
  company_address: z.string().default(""),
  company_zip_city: z.string().default(""),
  company_country: z.string().default("Deutschland"),
  contact_person: z.string().default(""),
  contact_phone: z.string().default(""),
  contact_email: z.string().default(""),
  delivery_term: z.string().default("EXW Werk"),
  payment_term: z.string().default("30 Tage netto"),
  validity_days: z.number().int().min(1).max(365).default(28),
});

export type CompanyProfile = z.infer<typeof companyProfileSchema>;

export const matchingPreferencesSchema = z.object({
  fuzzy_threshold: z.number().int().min(0).max(100).default(85),
  semantic_threshold: z.number().int().min(0).max(100).default(70),
});

export type MatchingPreferences = z.infer<typeof matchingPreferencesSchema>;

export const workflowPreferencesSchema = z.object({
  auto_refresh_pdf: z.boolean().default(true),
  confirm_before_reset: z.boolean().default(true),
  final_pdf_filename_template: z.string().default("Angebot_[Kunde].pdf"),
  email_subject_template: z.string().default("Angebot zu Ihrer Anfrage: [Betreff]"),
  email_body_template: z.string().default(
    "Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihre Anfrage. Anbei erhalten Sie unser Angebot.\n\nMit freundlichen Grüßen\n[Absender]"
  ),
  use_llm_email_body: z.boolean().default(false),
  llm_email_body_style_hint: z.string().max(280).default(""),
});

export type WorkflowPreferences = z.infer<typeof workflowPreferencesSchema>;

export const appSettingsSchema = z.object({
  company: companyProfileSchema,
  matching: matchingPreferencesSchema,
  workflow: workflowPreferencesSchema,
});

export type AppSettings = z.infer<typeof appSettingsSchema>;
