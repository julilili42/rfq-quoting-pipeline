import { z } from "zod";

/**
 * zod schemas for the Anfrage / Position model.
 *
 * The shapes mirror `quoting/core/schema.py`. We use `passthrough()` for
 * forward-compatibility — if the backend adds a field, requests still
 * succeed, but the new field won't appear in our types until we extend
 * the schema explicitly.
 */

export const confidenceSchema = z.enum(["high", "medium", "low"]);
export type Confidence = z.infer<typeof confidenceSchema>;

export const evidenceSchema = z.object({
  source_file: z.string().nullable().optional(),
  source_page: z.number().int().nullable().optional(),
  source_row: z.number().int().nullable().optional(),
  source_quote: z.string().nullable().optional(),
});
export type Evidence = z.infer<typeof evidenceSchema>;

export const positionSchema = z
  .object({
    pos_nr: z.number().int(),
    artikelnummer: z.string(),
    bezeichnung: z.string().default(""),
    menge: z.number(),
    einheit: z.string(),
    liefertermin: z.string().nullable().optional(),
    lieferzeit: z.string().nullable().optional(),
    lieferwerk: z.string().nullable().optional(),
    werkstoff: z.string().nullable().optional(),
    werkstoff_alternativen: z.array(z.string()).default([]),
    zeichnungsnummer: z.string().nullable().optional(),
    abmessungen: z.string().nullable().optional(),
    gewicht_stueck_kg: z.number().nullable().optional(),
    ist_zertifikat: z.boolean().default(false),
    confidence: confidenceSchema,
    source_quote: z.string().default(""),
    source_file: z.string().nullable().optional(),
    source_page: z.number().int().nullable().optional(),
    source_row: z.number().int().nullable().optional(),
  })
  .passthrough();

export type Position = z.infer<typeof positionSchema>;

export const anfrageSchema = z
  .object({
    vorgangsnummer: z.string().nullable().optional(),
    belegnummer: z.string().nullable().optional(),
    datum: z.string().nullable().optional(),
    kunde_firma: z.string().nullable().optional(),
    kunde_ansprechpartner: z.string().nullable().optional(),
    kunde_email: z.string().nullable().optional(),
    kundennummer: z.string().nullable().optional(),
    incoterms: z.string().nullable().optional(),
    zahlungsbedingungen: z.string().nullable().optional(),
    positionen: z.array(positionSchema).default([]),
    unsicherheiten: z.array(z.string()).default([]),
    header_evidence: z.record(evidenceSchema).default({}),
  })
  .passthrough();

export type Anfrage = z.infer<typeof anfrageSchema>;
