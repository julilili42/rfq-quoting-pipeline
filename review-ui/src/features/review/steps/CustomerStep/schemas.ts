import { z } from "zod";
import { anfrageSchema } from "@/shared/schemas/anfrage";

/**
 * Form schema for the customer section in the combined request-data step.
 *
 * Editable subset of the Anfrage — derived via .pick() so the form
 * stays in sync if the backend renames a customer-header field.
 */
export const customerFormSchema = anfrageSchema
  .pick({
    kunde_firma: true,
    kunde_ansprechpartner: true,
    kunde_email: true,
    kundennummer: true,
    belegnummer: true,
    datum: true,
    incoterms: true,
    zahlungsbedingungen: true,
  })
  .strip();

export type CustomerFormValues = z.infer<typeof customerFormSchema>;
