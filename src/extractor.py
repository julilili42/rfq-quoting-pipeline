"""
Extraktionsmodul
================
Das Herzstück: schickt PDF/Excel/Mail-Body an das LLM und validiert die
Antwort gegen ein striktes Pydantic-Schema.

WICHTIG:
- Nutzt KEIN OCR/MarkItDown für PDFs, sondern gibt sie direkt an ein
  Vision-fähiges LLM.
- Unterstützt zwei Provider:
  1. Gemini
  2. Azure OpenAI / Nexus

Provider-Umschaltung per Env:
- LLM_PROVIDER=gemini   -> nutzt GOOGLE_API_KEY
- LLM_PROVIDER=azure    -> nutzt NEXUS_API_KEY
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Optional imports, damit die Datei auch dann importierbar bleibt,
# wenn nur einer der beiden Provider installiert ist.
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import openai
except ImportError:
    openai = None


# ================================
# PYDANTIC-SCHEMA FÜR DIE ANFRAGE
# ================================

class Position(BaseModel):
    """Einzelne Position aus einer Preisanfrage."""
    pos_nr: int = Field(description="Laufende Positionsnummer (1, 2, 3, ...)")
    artikelnummer: str = Field(
        description="Artikel-/Sachnummer; leer wenn fehlt")
    bezeichnung: str = Field(
        description="Produktbezeichnung in Originalsprache")
    menge: float
    einheit: str = Field(description='z.B. "Stück", "kg", "m"')
    liefertermin: Optional[str] = Field(
        None, description="ISO-Datum YYYY-MM-DD falls angegeben"
    )
    werkstoff: Optional[str] = None
    werkstoff_alternativen: list[str] = Field(
        default_factory=list,
        description='Alternativ-Werkstoffe bei "wahlweise aus X, Y oder Z"',
    )
    zeichnungsnummer: Optional[str] = None
    abmessungen: Optional[str] = None
    gewicht_stueck_kg: Optional[float] = None
    ist_zertifikat: bool = Field(
        False,
        description="True wenn Position ein Prüfzeugnis/Zertifikat ist, keine Ware",
    )
    confidence: Literal["high", "medium", "low"]
    source_quote: str = Field(
        description="Wörtliches Zitat aus dem Dokument (max 150 Zeichen) für Audit"
    )


class Anfrage(BaseModel):
    """Komplette extrahierte Preisanfrage."""
    vorgangsnummer: Optional[str] = None
    belegnummer: Optional[str] = None
    datum: Optional[str] = Field(None, description="ISO-Datum YYYY-MM-DD")
    kunde_firma: Optional[str] = None
    kunde_ansprechpartner: Optional[str] = None
    kunde_email: Optional[str] = None
    incoterms: Optional[str] = None
    zahlungsbedingungen: Optional[str] = None
    positionen: list[Position]
    unsicherheiten: list[str] = Field(
        default_factory=list,
        description="Punkte, die das Modell nicht eindeutig extrahieren konnte",
    )


# ================================
# KONFIGURATION
# ================================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# Azure / Nexus
AZURE_ENDPOINT = os.getenv(
    "AZURE_OPENAI_ENDPOINT",
    "https://genai-nexus.api.corpinter.net/",
)
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5-mini")

for m in genai.list_models():
    print(m.name)

# Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")


SYSTEM_PROMPT = """\
Du bist ein Experte für die Analyse von Preisanfragen (RFQs) im industriellen B2B-Umfeld,
speziell für Kunststoff- und Metallteile. Aus dem gegebenen Dokument extrahierst du
strukturierte Positionsdaten.

SPRACHE:
- Erkenne die Sprache des Dokuments automatisch.
- Gib Bezeichnungen, Werkstoffe, Zeichnungsnummern in Originalsprache aus.
- Übersetze NICHTS.

EXTRAKTIONSREGELN:
1. Jede Zeile der Positionstabelle wird zu EINER Position in der Ausgabe.
   Achte besonders darauf, dass Spalten korrekt zugeordnet werden - Artikelnummer,
   Beschreibung, Menge und Termin gehören zur gleichen Position.

2. Artikelnummer/Sachnummer: Kann verschiedene Labels haben (Artikelnr., Part Number,
   Material Number, Item No., Sachnummer, SAP-Nr.). Leerzeichen in Nummern entfernen.
   Falls nicht vorhanden: leerer String.

3. Werkstoff: Extrahiere den Hauptwerkstoff (z.B. "PTFE mit 15% Graphit").
   Bei "wahlweise aus A, B oder C" -> werkstoff=null, werkstoff_alternativen=[A, B, C].

4. Zeichnungsnummer: Suche nach Mustern wie "nach Zeichnung XYZ", "Dwg No.", "Ausg. X".
   Bei mehreren Zeichnungsverweisen den primären nehmen.

5. Prüfzeugnisse/Zertifikate (z.B. "Abnahmeprüfzeugnis nach DIN EN 10204"):
   ist_zertifikat=true. Das ist KEINE physische Ware, sondern ein Dokument.

6. CONFIDENCE:
   - high:   Alle Pflichtfelder klar aus dem Dokument extrahierbar
   - medium: Mindestens ein Feld musste interpretiert/inferiert werden
   - low:    Signifikante Unsicherheit; Feld in "unsicherheiten" erklären

7. source_quote: Max 150 Zeichen wörtlich aus dem Dokument. Das ist für Audit/Review
   wichtig - damit der Sachbearbeiter sofort sieht, woher die Extraktion stammt.

AUSGABE: Ausschließlich valides JSON gemäß dem übergebenen Schema. KEIN Markdown-Codeblock,
KEINE Erklärungen, NUR das JSON-Objekt.
"""


# ================================
# PUBLIC API
# ================================

def extrahiere_anfrage(
    attachments: list[Path],
    mail_body: str = "",
) -> Anfrage:
    """
    Extrahiert eine strukturierte Anfrage aus Mail + Attachments.

    PDFs werden direkt als Bilder an ein Vision-Modell gegeben.
    Excel-Dateien werden als Markdown-Tabelle serialisiert.
    """
    provider = LLM_PROVIDER

    if provider == "gemini":
        return _extrahiere_mit_gemini(attachments=attachments, mail_body=mail_body)

    if provider == "azure":
        return _extrahiere_mit_azure(attachments=attachments, mail_body=mail_body)

    raise ValueError(
        f"Unbekannter LLM_PROVIDER='{provider}'. Erlaubt sind: 'gemini', 'azure'."
    )


# ================================
# GEMINI
# ================================

def _extrahiere_mit_gemini(
    attachments: list[Path],
    mail_body: str = "",
) -> Anfrage:
    if genai is None:
        raise ImportError(
            "google-generativeai ist nicht installiert. "
            "Installiere z.B. mit: pip install google-generativeai"
        )

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY fehlt. Setze den Key oder stelle LLM_PROVIDER=azure ein."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt_parts: list[str] = [SYSTEM_PROMPT.strip(), ""]

    if mail_body and mail_body.strip():
        prompt_parts.append("=== MAIL-BODY ===")
        prompt_parts.append(mail_body.strip())
        prompt_parts.append("")

    gemini_parts: list[object] = []

    for att in attachments:
        ext = att.suffix.lower().lstrip(".")

        if ext == "pdf":
            prompt_parts.append(f"=== ANHANG {att.name} (PDF) ===")
            prompt_parts.append(
                "Die folgenden Bilder sind Seiten desselben PDF-Dokuments. "
                "Bitte Reihenfolge und Tabellenlayout beachten."
            )
            prompt_parts.append("")
            gemini_parts.extend(_pdf_to_gemini_parts(att))

        elif ext in ("xlsx", "xls"):
            prompt_parts.append(f"=== ANHANG {att.name} (Excel) ===")
            prompt_parts.append(_excel_to_markdown(att))
            prompt_parts.append("")

        elif ext == "csv":
            prompt_parts.append(f"=== ANHANG {att.name} (CSV) ===")
            prompt_parts.append(att.read_text(
                encoding="utf-8", errors="replace"))
            prompt_parts.append("")

        elif ext in ("png", "jpg", "jpeg"):
            prompt_parts.append(f"=== ANHANG {att.name} (Bild) ===")
            prompt_parts.append("")
            gemini_parts.append(_image_to_gemini_part(att))

    prompt_parts.append(
        "Extrahiere die Preisanfrage gemäß folgendem JSON-Schema. "
        "Antworte NUR mit validem JSON:"
    )
    prompt_parts.append(json.dumps(
        Anfrage.model_json_schema(), indent=2, ensure_ascii=False))

    prompt = "\n".join(prompt_parts)

    response = model.generate_content(
        [prompt, *gemini_parts],
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )

    raw = getattr(response, "text", None)
    if not raw:
        raise ValueError("Gemini hat keine Textantwort zurückgegeben.")

    raw_json = _extract_json_object(raw)
    return Anfrage.model_validate_json(raw_json)


def _pdf_to_gemini_parts(pdf_pfad: Path) -> list[dict]:
    """
    Rendert jede PDF-Seite als PNG und gibt Gemini-kompatible Bildteile zurück.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_pfad)
    parts: list[dict] = []

    try:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            parts.append(
                {
                    "mime_type": "image/png",
                    "data": img_bytes,
                }
            )
    finally:
        doc.close()

    return parts


def _image_to_gemini_part(img_pfad: Path) -> dict:
    mime = "image/png" if img_pfad.suffix.lower() == ".png" else "image/jpeg"
    return {
        "mime_type": mime,
        "data": img_pfad.read_bytes(),
    }


# ================================
# AZURE OPENAI / NEXUS
# ================================

def _extrahiere_mit_azure(
    attachments: list[Path],
    mail_body: str = "",
) -> Anfrage:
    if openai is None:
        raise ImportError(
            "openai ist nicht installiert. Installiere z.B. mit: pip install openai"
        )

    api_key = os.getenv("NEXUS_API_KEY")
    if not api_key:
        raise ValueError(
            "NEXUS_API_KEY fehlt. Setze den Key oder stelle LLM_PROVIDER=gemini ein."
        )

    llm_client = openai.AzureOpenAI(
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=api_key,
    )

    content_parts: list[dict] = []

    if mail_body and mail_body.strip():
        content_parts.append(
            {
                "type": "text",
                "text": f"=== MAIL-BODY ===\n{mail_body.strip()}",
            }
        )

    for att in attachments:
        ext = att.suffix.lower().lstrip(".")

        if ext == "pdf":
            content_parts.extend(_pdf_to_openai_blocks(att))

        elif ext in ("xlsx", "xls"):
            content_parts.append(
                {
                    "type": "text",
                    "text": f"=== ANHANG {att.name} (Excel) ===\n{_excel_to_markdown(att)}",
                }
            )

        elif ext == "csv":
            content_parts.append(
                {
                    "type": "text",
                    "text": (
                        f"=== ANHANG {att.name} (CSV) ===\n"
                        + att.read_text(encoding="utf-8", errors="replace")
                    ),
                }
            )

        elif ext in ("png", "jpg", "jpeg"):
            content_parts.append(_image_to_openai_block(att))

    content_parts.append(
        {
            "type": "text",
            "text": (
                "Extrahiere die Preisanfrage gemäß folgendem JSON-Schema. "
                "Antworte NUR mit validem JSON:\n\n"
                + json.dumps(Anfrage.model_json_schema(),
                             indent=2, ensure_ascii=False)
            ),
        }
    )

    response = llm_client.chat.completions.create(
        model=AZURE_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content_parts},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("Azure OpenAI hat keine Antwort zurückgegeben.")

    return Anfrage.model_validate_json(raw)


def _pdf_to_openai_blocks(pdf_pfad: Path) -> list[dict]:
    """
    Rendert jede PDF-Seite als PNG und gibt OpenAI/Azure-kompatible image_url-Blöcke zurück.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_pfad)
    blocks: list[dict] = [
        {
            "type": "text",
            "text": f"=== ANHANG {pdf_pfad.name} (PDF, {len(doc)} Seiten) ===",
        }
    ]

    try:
        for page_num, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.standard_b64encode(img_bytes).decode()

            blocks.append(
                {
                    "type": "text",
                    "text": f"--- PDF-Seite {page_num} ---",
                }
            )
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}",
                        "detail": "high",
                    },
                }
            )
    finally:
        doc.close()

    return blocks


def _image_to_openai_block(img_pfad: Path) -> dict:
    mime = "image/png" if img_pfad.suffix.lower() == ".png" else "image/jpeg"
    img_b64 = base64.standard_b64encode(img_pfad.read_bytes()).decode()
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime};base64,{img_b64}",
            "detail": "high",
        },
    }


# ================================
# GEMEINSAME HILFSFUNKTIONEN
# ================================

def _extract_json_object(raw: str) -> str:
    """
    Extrahiert das erste JSON-Objekt aus einer Modellantwort.
    Nützlich für Gemini, falls trotz response_mime_type zusätzlicher Text kommt.
    """
    raw = raw.strip()

    if raw.startswith("{") and raw.endswith("}"):
        return raw

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Kein JSON-Objekt in Modellantwort gefunden:\n{raw}")

    return match.group(0)


def _excel_to_markdown(xlsx_pfad: Path) -> str:
    """
    Serialisiert Excel-Sheets als Markdown-Tabellen.
    Für einfache tabellarische Positionslisten ist das deterministischer als Vision.
    """
    try:
        import pandas as pd
    except ImportError:
        return f"[pandas nicht installiert - kann {xlsx_pfad.name} nicht lesen]"

    parts: list[str] = []
    xls = pd.ExcelFile(xlsx_pfad)

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        parts.append(f"\n--- Sheet: {sheet_name} ---\n")
        parts.append(df.to_markdown(index=False))

    return "\n".join(parts)
