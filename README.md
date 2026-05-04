# ElringKlinger Quoting Pipeline – Installation & Startup

AI-assisted generator for quotation drafts: RFQ in, quotation draft out.

```text
ingestion → extraction → matching → pricing → output
            (LLM)        (fuzzy)    (rules)
```

Only the extraction step uses an LLM. Matching and pricing are deterministic and auditable.

## Prerequisites

- Python 3.10+
- Node.js 20+
- `uv`, if you want to use the root command `npm run dev`
- API key for Gemini or Azure OpenAI
- Optional for Outlook tests with a public HTTPS URL: `cloudflared`

Cloudflare Tunnel is not required for testing the Review UI locally in the browser or upload files directly through the dashboard. For Outlook sideloading, a tunnel is required, since PDF attachments need a publicly reachable HTTPS URL.

## Installation

```bash
git clone https://github.com/julilili42/Business-and-AI
cd Business-and-AI
```

### Recommended for the existing root startup command

The root command `npm run dev` starts the API with `uv run python run_review_api.py`. For that, `uv` must be installed.

```bash
python -m pip install uv
uv sync
cp env.example .env
```

Then add the correct provider and API key to `.env`, for example:

```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...

# or
LLM_PROVIDER=azure
NEXUS_API_KEY=...
```

### Alternative without `uv`

If you do not want to use `uv`, start the backend and frontends separately.

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -e ".[dev]"
cp env.example .env
python run_review_api.py
```

### Install the frontends

Run once from the project root:

```bash
npm install
npm --prefix review-ui install
npm --prefix outlook-ui install
```

### Start the application
Start everything via:

```bash
npm run dev
```
in the project root. 
This starts in parallel:

- FastAPI: `http://127.0.0.1:8000`
- Review UI: `http://localhost:5174`
- Outlook UI: `http://localhost:5173`

The actual ports are always shown in the terminal output.

## Sideload the Outlook add-in

1. Start the application:

```bash
npm run dev
```

2. If needed, start the Cloudflare Tunnel and set `.tunnel_url`.

3. Open the Outlook sideload page:

```text
https://aka.ms/olksideload
```

Alternatively, use the official Microsoft documentation:

```text
https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/sideload-outlook-add-ins-for-testing
```

4. Open Outlook add-in management.

5. Upload `outlook-ui/manifest.xml` as a custom add-in.

6. Open an email with an RFQ attachment and run the add-in button.

7. Workflow:

```text
Open email → Create draft → Open Review UI → review/approve → create quotation email
```

Notes:

- If sideloading is blocked by the organization, a Microsoft 365 or Exchange admin must allow it.
- In some Outlook clients, it can take a short while until a newly sideloaded add-in appears.
- If the add-in does not load, first check `manifest.xml`: `SourceLocation` must point to the running Outlook UI.

## Tests

```bash
pytest
pytest tests/unit
```

With `uv`:

```bash
uv run pytest
uv run pytest tests/unit
```