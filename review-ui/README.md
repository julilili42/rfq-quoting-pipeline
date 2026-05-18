# review-ui-react

React-Migration der bisherigen Streamlit-Review-UI für das ElringKlinger
Quoting-System. Die Geschäftslogik (Extraction, Matching, Pricing, PDF)
bleibt komplett im Python-Backend; dieses Projekt ersetzt nur das
Frontend und nutzt eine Handvoll neuer FastAPI-Endpunkte.

## Struktur

```
src/
├── app/                    # Provider-Komposition + Router
├── features/
│   ├── dashboard/          # Übersicht aller Reviews
│   ├── review/             # Review-Detail mit 3 Steps
│   │   ├── components/     # Hero, Breadcrumb, StepIndicator …
│   │   ├── hooks/          # useReview, useApproval, useReviewMutations
│   │   ├── stores/         # Zustand-Store für Per-Review-UI
│   │   └── steps/
│   │       ├── PositionsStep/
│   │       ├── CustomerStep/
│   │       └── ApprovalStep/
│   ├── settings/
│   └── upload/
└── shared/
    ├── api/                # Typed fetch wrappers
    ├── schemas/            # zod-Schemas (single source of truth)
    ├── components/
    │   ├── ui/             # shadcn-style Primitives (Button, Card …)
    │   ├── layout/         # AppShell, Sidebar, PageContainer
    │   ├── viewers/        # PdfViewer, MailBodyViewer, OriginalDocumentViewer
    │   └── feedback/       # LoadingState, EmptyState, ErrorState
    ├── lib/                # cn, format, env, pdfUrl
    └── stores/
```

## Tech-Stack

| Bereich         | Wahl                              |
| --------------- | --------------------------------- |
| UI              | Radix Primitives + Tailwind       |
| Forms           | react-hook-form + zod             |
| Server-State    | TanStack Query                    |
| Schemas         | zod (geteilt zwischen UI und API) |
| Routing         | React Router v6                   |
| Client-State    | Zustand                           |
| Icons           | lucide-react                      |
| PDF             | iframe + Cache-Busting            |
| Upload          | react-dropzone                    |

## Voraussetzungen

1. **Backend-Patch anwenden** — siehe `backend-patches/README.md`.
   Ohne `frontend_router.py` registriert zu haben, fehlen die
   neun Endpunkte, die diese App benötigt.
2. **FastAPI starten** — `python run_review_api.py` (oder vergleichbar).
   Default-Port: `8000`.

## Dev-Server

```bash
npm install
npm run dev
```

Öffnet `http://localhost:5173`. Vite proxiert `/api/*` auf
`http://127.0.0.1:8000`. Für Production-Setups die
Umgebungsvariable `VITE_API_BASE_URL` setzen.

## Build

```bash
npm run build
```

Resultiert in `dist/` und kann von einem beliebigen statischen
Webserver (FastAPI selbst, nginx, Caddy) ausgeliefert werden.

## Was gegenüber Streamlit anders ist

- **Auto-Save mit PDF-Rebuild**: Jede Editor-Änderung committet via
  `useSaveAndRegenerate`, das im selben API-Call die Anfrage speichert
  und das Draft-PDF neu rendert. Damit ist die Anforderung
  „Änderungen müssen bereits in der Draft-PDF sichtbar sein" sauber
  umgesetzt — kein Zusatz-Klick nötig.
- **Tabs für Original / Draft / Final**: ApprovalStep zeigt zwei
  parallele Tab-Strips (links Original, rechts Angebot). Final-Tab
  erscheint erst nach Freigabe; Draft bleibt immer mit AI-Warnung,
  Final immer ohne. Distinkte API-URLs (`/pdf/draft` vs `/pdf/final`)
  verhindern das alte Browser-Cache-Konflikt-Problem.
- **Vollbild-Modus**: `?focus=1` aktiviert eine isolierte Compare-View
  ohne Sidebar / Hero / Step-Indicator. Sauberer State-Erhalt.
- **Backend-First**: Filesystem-Scans (`review_loader`), Quotation-
  Rebuild (`quotation_flow`) und Direkt-Upload sind aus dem UI-Code
  ausgezogen und in HTTP-Endpunkte verlagert.

## Was als nächstes kommt

- [ ] Agent-Chat-Panel (kommerzielle Anpassungen via natürlicher Sprache)
- [ ] Tabellen-Vorschau für CSV/XLSX-Originale (TanStack Table)
- [ ] Stammdaten-Suche / Manuelles Re-Matching
- [ ] Export der Übersicht als CSV
