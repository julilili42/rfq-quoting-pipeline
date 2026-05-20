import { z } from "zod";

import type { components } from "@/shared/api-types";

/**
 * Types are the single source of truth from the FastAPI OpenAPI schema
 * (regenerated via `npm run gen:api`). The Zod schemas below are kept only
 * for runtime validation in the API client — if the wire format drifts
 * from these, TypeScript will fail where `anfrageSchema.parse(...)` is
 * assigned to one of the exported types.
 */

export type Evidence = components["schemas"]["Evidence"];
export type Position = components["schemas"]["Position"];
export type Anfrage = components["schemas"]["Anfrage"];
export type Anforderung = components["schemas"]["Anforderung"];
export type AnforderungKategorie = Anforderung["kategorie"];
export type Confidence = Position["confidence"];

export const confidenceSchema = z.enum(["high", "medium", "low"]);

export const evidenceSchema = z.object({
  source_file: z.string().nullable().optional(),
  source_page: z.number().int().nullable().optional(),
  source_row: z.number().int().nullable().optional(),
  source_quote: z.string().nullable().optional(),
});

export const positionSchema = z
  .object({
    pos_nr: z.number().int(),
    artikelnummer: z.string(),
    bezeichnung: z.string().default(""),
    menge: z.number(),
    einheit: z.string(),
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

export const anforderungKategorieSchema = z.enum([
  "zeichnung",
  "zertifikat",
  "verpackung",
  "logistik",
  "termin",
  "sonstige",
]);

export const anforderungSchema = z
  .object({
    text: z.string(),
    kategorie: anforderungKategorieSchema,
    pos_nr: z.number().int().nullable().optional(),
    source_quote: z.string().default(""),
  })
  .passthrough();

export const anfrageSchema = z
  .object({
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
    anforderungen: z.array(anforderungSchema).default([]),
    header_evidence: z.record(evidenceSchema).default({}),
  })
  .passthrough();
