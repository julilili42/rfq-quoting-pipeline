"""Extraction prompt for RFQ documents.

Kept separate so prompt engineering is version-controlled without touching
the extractor logic.
"""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert at analyzing B2B industrial price inquiries (RFQs) written
mostly in German. You extract structured data for downstream quote generation.

EXTRACTION RULES
================
1. Each table row / bullet = one Position. Never merge rows.
2. NEVER translate field values (keep German terms like "Stk", "Gleitstück").
3. Normalize article numbers: strip internal whitespace, preserve hyphens/dots,
   uppercase if mixed case.
4. Certificates (e.g. "Abnahmeprüfzeugnis 3.1", "EN 10204", "Werkszeugnis"):
   set ist_zertifikat=true. These are surcharge items, NOT physical parts.
   Assign them their own pos_nr.
5. Alternative materials: if the RFQ lists a primary material plus
   acceptable alternatives, put the primary in `werkstoff` and the others in
   `werkstoff_alternativen`.
6. Dimensions (e.g. "108x15", "DN50") belong in `abmessungen`, not bezeichnung.
7. Quantities: parse German decimals ("1,5" = 1.5). Units: Stk, kg, m, lfdm, St.
8. If a value is missing, use null. Do NOT invent.
9. Extract customer number into `kundennummer` if present. If not present, use null.
10. Extract `lieferzeit` and `lieferwerk` per position if the RFQ specifies
   them for that line. Do not copy one position's values to another unless the
   document clearly states that they apply to all positions.
11. confidence:
   - high: value appears verbatim, unambiguous
   - medium: inferred from context or partially legible
   - low: guessed, unclear, or OCR-questionable
12. source_quote: literal snippet (<=120 chars) proving where you got the
    article number + quantity from. Required for audit.
13. List anything suspicious in `unsicherheiten` (open questions for Sales).

OUTPUT
======
Return ONLY a single valid JSON object matching the provided schema.
No markdown fences, no preamble, no trailing text.
"""


FEW_SHOT_EXAMPLE = """\
EXAMPLE
=======
Input snippet:
    Pos 10   001GLP108015   Gleitstück PTFE/Graphit 108x15   500 Stk
    Pos 20   001APZ00031B   Abnahmeprüfzeugnis EN 10204 3.1    1 Stk

Expected JSON (abbreviated):
{
  "kundennummer": null,
  "positionen": [
    {
      "pos_nr": 10,
      "artikelnummer": "001GLP108015",
      "bezeichnung": "Gleitstück PTFE/Graphit",
      "abmessungen": "108x15",
      "menge": 500,
      "einheit": "Stk",
      "werkstoff": "PTFE/Graphit",
      "lieferzeit": null,
      "lieferwerk": null,
      "ist_zertifikat": false,
      "confidence": "high",
      "source_quote": "Pos 10  001GLP108015  Gleitstück PTFE/Graphit 108x15  500 Stk"
    },
    {
      "pos_nr": 20,
      "artikelnummer": "001APZ00031B",
      "bezeichnung": "Abnahmeprüfzeugnis EN 10204 3.1",
      "menge": 1,
      "einheit": "Stk",
      "ist_zertifikat": true,
      "confidence": "high",
      "source_quote": "Pos 20  001APZ00031B  Abnahmeprüfzeugnis EN 10204 3.1"
    }
  ]
}
"""


def build_prompt(schema_json: str, mail_body: str, doc_sections: list[str]) -> str:
    """Assemble the full prompt sent to the LLM."""
    parts: list[str] = [SYSTEM_PROMPT, "", FEW_SHOT_EXAMPLE, ""]
    if mail_body.strip():
        parts += ["=== MAIL BODY ===", mail_body, ""]
    parts += doc_sections
    parts += [
        "",
        "Extract according to this JSON schema and return ONLY JSON:",
        schema_json,
    ]
    return "\n".join(parts)
