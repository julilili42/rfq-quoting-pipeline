import type { Page, Route } from "@playwright/test";

const REVIEW_ID = "demo-review";
const BLOCKED_REVIEW_ID = "blocked-review";

const baseAnfrage = {
  belegnummer: "2026-50422",
  datum: "11.05.2026",
  kunde_firma: "Gohmann & Co. GmbH",
  kunde_ansprechpartner: "Felix Hochstein",
  kunde_email: "f.hochstein@example.com",
  kundennummer: "1234",
  incoterms: "FCA (Incoterms 2020)",
  zahlungsbedingungen: "14 Tage 2% Skonto, 30 Tage netto",
  unsicherheiten: [],
  header_evidence: {
    kunde_firma: {
      source_file: "mail",
      source_quote: "Gohmann & Co. GmbH",
    },
  },
  positionen: [
    {
      pos_nr: 1,
      artikelnummer: "001GLP108015",
      bezeichnung: "Gleitstueck fuer Wiegentraeger",
      menge: 100,
      einheit: "Stueck",
      lieferzeit: "06.05.2026",
      lieferwerk: "Dettingen",
      werkstoff: "PTFE/Graphit",
      werkstoff_alternativen: [],
      zeichnungsnummer: "012300124820-04.61",
      abmessungen: "108 x 15 mm",
      gewicht_stueck_kg: 0.3,
      ist_zertifikat: false,
      confidence: "high",
      source_quote: "001GLP108015 Gleitstueck 100 Stueck",
      source_file: "mail",
      source_page: null,
      source_row: null,
    },
  ],
};

type ApiState = {
  approvalState: "draft_generated" | "approved";
  anfrage: typeof baseAnfrage;
  manualOverrides: unknown[];
};

const baseMatches = [
  {
    pos_nr: 1,
    status: "exact",
    score: 1,
    matched_artikelnr: "001GLP108015",
    matched_bezeichnung: "Gleitstueck fuer Wiegentraeger nach Zeichnung",
    matched_row: {
      artikel_nr: "001GLP108015",
      bezeichnung: "Gleitstueck fuer Wiegentraeger nach Zeichnung",
      basispreis_eur: 24.5,
      zkalk_offset_eur: 1.2,
    },
  },
];

const stammdatenRows = [
  {
    artikel_nr: "002GLS082003",
    bezeichnung: "Gleitstueck variabel 82x3",
    werkstoff: "PTFE",
    abmessungen: "82 x 3 mm",
    einheit: "Stueck",
    basispreis_eur: 18.75,
    preis_min_eur: 18.75,
    preis_max_eur: 18.75,
    n_offers: 4,
    sales_group: "VG 31",
    material_group: "Gleitstuecke",
  },
];

const baseQuotation = {
  kunde_firma: baseAnfrage.kunde_firma,
  kunde_ansprechpartner: baseAnfrage.kunde_ansprechpartner,
  kunde_email: baseAnfrage.kunde_email,
  kundennummer: baseAnfrage.kundennummer,
  belegnummer: baseAnfrage.belegnummer,
  incoterms: baseAnfrage.incoterms,
  zahlungsbedingungen: baseAnfrage.zahlungsbedingungen,
  items: [
    {
      pos_nr: 1,
      artikel_nr: "001GLP108015",
      bezeichnung: "Gleitstueck fuer Wiegentraeger nach Zeichnung",
      menge: 100,
      einheit: "Stueck",
      einzelpreis: 24.48,
      rabatt_prozent: 5,
      gesamtpreis: 2447.5,
      bemerkung: "",
      basispreis_eur: 24.5,
      margin_eur: 120,
      margin_pct: 4.9,
    },
  ],
  gesamtsumme: 2447.5,
  waehrung: "EUR",
  warnungen: [],
};

const mail = {
  subject: "Preisanfrage 2026-50422",
  from: "Felix Hochstein <f.hochstein@example.com>",
  body: "Bitte bieten Sie 100 Stueck 001GLP108015 an.",
  attachments: [{ name: "Anfrage.pdf", contentType: "application/pdf", size: 1234 }],
};

const progress = {
  status: "completed",
  current_step: "Review bereit",
  current_detail: "Pipeline abgeschlossen",
  progress_percent: 100,
  updated_at: "2026-05-11T11:00:50.277Z",
  steps: [
    { name: "Mail vorbereiten", status: "completed", detail: "", updated_at: null },
    { name: "Extraktion", status: "completed", detail: "1 Position", updated_at: null },
    { name: "Matching", status: "completed", detail: "1 exakt, 0 kein Treffer", updated_at: null },
    { name: "Preisberechnung", status: "completed", detail: "Gesamt: 2447.50 EUR", updated_at: null },
    { name: "PDF-Rendering", status: "completed", detail: "", updated_at: null },
  ],
  result: null,
  error: null,
};

const baseSettings = {
  company: {
    company_name: "Demo GmbH",
    company_address: "Musterstrasse 1",
    company_zip_city: "12345 Musterstadt",
    company_country: "Deutschland",
    contact_person: "Demo User",
    contact_phone: "+49 30 123456",
    contact_email: "demo@example.com",
    delivery_term: "EXW Werk",
    payment_term: "30 Tage netto",
    validity_days: 28,
  },
  matching: {
    fuzzy_threshold: 85,
    semantic_threshold: 70,
  },
  workflow: {
    auto_refresh_pdf: true,
    confirm_before_reset: true,
    final_pdf_filename_template: "Angebot_[Kunde].pdf",
    email_subject_template: "Angebot zu Ihrer Anfrage: [Betreff]",
    email_body_template: "Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie unser Angebot.",
  },
};

export async function mockReviewApi(page: Page) {
  const state: ApiState = {
    approvalState: "draft_generated",
    anfrage: clone(baseAnfrage),
    manualOverrides: [],
  };
  let settings = clone(baseSettings);

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const path = url.pathname;

    if (!path.startsWith("/api/")) {
      return route.continue();
    }

    if (method === "GET" && path === "/api/settings") {
      return json(route, settings);
    }

    if (method === "PUT" && path === "/api/settings") {
      settings = await request.postDataJSON();
      return json(route, settings);
    }

    if (method === "GET" && path === "/api/reviews") {
      return json(route, [
        {
          review_id: REVIEW_ID,
          created_at: "2026-05-11T11:00:35.275Z",
          updated_at: "2026-05-11T11:00:50.277Z",
          subject: mail.subject,
          sender: mail.from,
          positions: 1,
          confidence_high: 1,
          confidence_medium: 0,
          confidence_low: 0,
          matches_exact: 1,
          matches_fuzzy: 0,
          matches_semantic: 0,
          matches_no_match: 0,
          total_eur: baseQuotation.gesamtsumme,
          currency: "EUR",
          status: "pdf_bereit",
          has_pdf: true,
          manual_overrides_count: 0,
          extracted_articles: ["001GLP108015"],
        },
      ]);
    }

    if (method === "GET" && path === `/api/reviews/${REVIEW_ID}`) {
      return json(route, {
        review_id: REVIEW_ID,
        created_at: "2026-05-11T11:00:35.275Z",
        anfrage: state.anfrage,
        original_anfrage: baseAnfrage,
        matches: matchesFor(state.anfrage),
        quotation: quotationFor(state.anfrage),
        manual_overrides: state.manualOverrides,
        mail,
        has_draft_pdf: true,
        has_final_pdf: state.approvalState === "approved",
      });
    }

    if (method === "GET" && path === `/api/reviews/${BLOCKED_REVIEW_ID}`) {
      return json(route, {
        review_id: BLOCKED_REVIEW_ID,
        created_at: "2026-05-11T11:00:35.275Z",
        anfrage: {
          ...baseAnfrage,
          positionen: [{ ...baseAnfrage.positionen[0], artikelnummer: "UNKNOWN", confidence: "low" }],
        },
        original_anfrage: {
          ...baseAnfrage,
          positionen: [{ ...baseAnfrage.positionen[0], artikelnummer: "UNKNOWN", confidence: "low" }],
        },
        matches: [{ pos_nr: 1, status: "no_match", score: 0, matched_artikelnr: null, matched_bezeichnung: null, matched_row: null }],
        quotation: { ...baseQuotation, items: [], gesamtsumme: 0, warnungen: ["Pos 1: no match"] },
        manual_overrides: [],
        mail,
        has_draft_pdf: true,
        has_final_pdf: false,
      });
    }

    if (method === "GET" && path.endsWith("/status")) {
      return json(route, { review_id: path.split("/")[3], ...progress });
    }

    if (method === "GET" && path.endsWith("/approval")) {
      return json(route, approvalPayload(state));
    }

    if (method === "POST" && path === `/api/reviews/${REVIEW_ID}/finalize`) {
      state.approvalState = "approved";
      return json(route, { final_pdf_path: "Angebot_demo_FINAL.pdf" });
    }

    if (method === "POST" && path.endsWith("/regenerate")) {
      return json(route, quotationFor(state.anfrage));
    }

    if (method === "PUT" && path.endsWith("/anfrage")) {
      state.anfrage = await request.postDataJSON();
      return json(route, state.anfrage);
    }

    if (method === "PUT" && path.endsWith("/overrides")) {
      state.manualOverrides = await request.postDataJSON();
      return json(route, state.manualOverrides);
    }

    if (method === "GET" && path === "/api/stammdaten/search") {
      return json(route, stammdatenRows);
    }

    if (method === "POST" && path === `/api/reviews/${REVIEW_ID}/match-override`) {
      const payload = await request.postDataJSON();
      const row = stammdatenRows.find((item) => item.artikel_nr === payload.artikel_nr) ?? stammdatenRows[0];
      return json(route, {
        pos_nr: payload.pos_nr,
        matched_artikelnr: row.artikel_nr,
        matched_bezeichnung: row.bezeichnung,
      });
    }

    if (path.includes("/pdf/") || path.includes("/attachment/")) {
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: "%PDF-1.4\n% mocked pdf\n",
      });
    }

    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled ${method} ${path}` }) });
  });
}

function matchesFor(anfrage: typeof baseAnfrage) {
  return anfrage.positionen.map((position) => {
    if (position.artikelnummer === "001GLP108015") {
      return { ...baseMatches[0], pos_nr: position.pos_nr };
    }
    const row = stammdatenRows.find((item) => item.artikel_nr === position.artikelnummer);
    if (row) {
      return {
        pos_nr: position.pos_nr,
        status: "exact",
        score: 1,
        matched_artikelnr: row.artikel_nr,
        matched_bezeichnung: row.bezeichnung,
        matched_row: row,
      };
    }
    return {
      pos_nr: position.pos_nr,
      status: "no_match",
      score: 0,
      matched_artikelnr: null,
      matched_bezeichnung: null,
      matched_row: null,
    };
  });
}

function quotationFor(anfrage: typeof baseAnfrage) {
  return {
    ...baseQuotation,
    items: anfrage.positionen.map((position) => {
      if (position.pos_nr === 1) return baseQuotation.items[0];
      return {
        pos_nr: position.pos_nr,
        artikel_nr: position.artikelnummer,
        bezeichnung: position.bezeichnung,
        menge: position.menge,
        einheit: position.einheit,
        einzelpreis: 18.75,
        rabatt_prozent: 0,
        gesamtpreis: 18.75 * position.menge,
        bemerkung: "",
        basispreis_eur: 18.75,
        margin_eur: 0,
        margin_pct: 0,
      };
    }),
    gesamtsumme: anfrage.positionen.reduce(
      (sum, position) => sum + (position.pos_nr === 1 ? 2447.5 : 18.75 * position.menge),
      0,
    ),
  };
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

function approvalPayload(state: ApiState) {
  if (state.approvalState === "approved") {
    return {
      state: "approved",
      approved_by: "Demo User",
      approved_at: "2026-05-11T11:03:11.478Z",
      sent_at: null,
      changed_fields: [],
      final_pdf_path: "Angebot_demo_FINAL.pdf",
      warning_acknowledged: true,
      history: [],
    };
  }
  return {
    state: "draft_generated",
    approved_by: null,
    approved_at: null,
    sent_at: null,
    changed_fields: [],
    final_pdf_path: null,
    warning_acknowledged: false,
    history: [],
  };
}

function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export const ids = {
  review: REVIEW_ID,
  blockedReview: BLOCKED_REVIEW_ID,
};
