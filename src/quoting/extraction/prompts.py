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
14. Evidence fields per position (fill when determinable, leave null otherwise):
    - source_file: filename as shown in the section header (e.g. "Anfrage.pdf"),
      or "mail" if the data came from the mail body.
    - source_page: 1-indexed page number for PDF sources (use only when the PDF
      has visible page numbers or you are certain of the page).
    - source_row: 0-indexed data row from the "Row" column in Excel/CSV tables.
    - Vision inputs are labelled "Image N: PDF <filename>, page P of M" or
      "Image N: image file <filename>". Use these labels to map image evidence
      to source_file and source_page.
15. header_evidence: for each extracted Anfrage header field (e.g. "kunde_firma",
    "belegnummer", "datum"), provide an Evidence object with the same fields as
    above. Only include fields where you found clear evidence; omit the rest.

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


def build_prompt_parts(
    schema_json: str,
    mail_body: str,
    doc_sections: list[str],
    own_company_context: str = "",
) -> tuple[str, str]:
    """Split the prompt into a stable (cacheable) prefix and a variable suffix.

    The stable part — system rules + few-shot example + schema — is identical
    across every extraction call within a process. Gemini context caching
    keys on this prefix so input-token cost drops to ~25 % and TTFT shortens.
    The variable part carries own-company context plus actual mail + document content.
    """
    stable_parts = [
        SYSTEM_PROMPT,
        "",
        FEW_SHOT_EXAMPLE,
        "",
        "Extract according to this JSON schema and return ONLY JSON:",
        schema_json,
    ]
    variable_parts: list[str] = []
    if own_company_context.strip():
        variable_parts += [
            "=== OUR COMPANY / DO NOT EXTRACT AS CUSTOMER ===",
            own_company_context,
            "",
        ]
    if mail_body.strip():
        variable_parts += ["=== MAIL BODY ===", mail_body, ""]
    variable_parts += doc_sections
    return "\n".join(stable_parts), "\n".join(variable_parts)


def build_prompt(
    schema_json: str,
    mail_body: str,
    doc_sections: list[str],
    own_company_context: str = "",
) -> str:
    """Assemble the full prompt sent to the LLM (single-string form)."""
    stable, variable = build_prompt_parts(
        schema_json,
        mail_body,
        doc_sections,
        own_company_context,
    )
    return f"{stable}\n\n{variable}" if variable else stable
