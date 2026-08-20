# Scrapted

Scrapted is a focused AI-assisted scraping MVP that recovers when a CSS selector has gone stale. Give it a public URL, describe the data you need, and optionally provide the selector you expected. It tries that selector first, then asks an AI model to choose from verified DOM candidates only when recovery is needed.

## Architecture

- `backend/` is a FastAPI API that validates URLs, blocks common SSRF targets, fetches static HTML with Scrapling, prepares bounded DOM candidates, and verifies every AI selection against the parsed page.
- `frontend/` is a Vite React app with a source-file interface. It renders the actual form, trace, errors, and result inside visible HTML-like structure.
- Gemini is isolated behind `app/services/ai.py`. The default model is `gemini-3.5-flash-lite`, but the rest of the scraper does not depend on Gemini-specific types.

## Prerequisites

- Python 3.10. The repository includes `/usr/bin/python3.10` in this workspace; do not use the default Python 3.14 runtime.
- Node.js 20 or newer.
- A Gemini API key for AI recovery and discovery. Direct CSS-selector matches work without one.

## Run locally

Backend:

```bash
cd backend
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
scrapling install
cp .env.example .env
uvicorn app.main:app --reload
```

Frontend, in another terminal:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.

## Environment variables

Backend variables live in `backend/.env`:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | For AI flow | Empty | Gemini API key. |
| `GEMINI_MODEL` | No | `gemini-3.5-flash-lite` | Model used for recovery. |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated explicit browser origins. |
| `CORS_ORIGIN_REGEX` | No | Localhost ports only | Allows Vite development servers on localhost or 127.0.0.1 at any port. |
| `SCRAPE_TIMEOUT_SECONDS` | No | `10` | Per-request Scrapling timeout. |
| `MAX_RESPONSE_BYTES` | No | `0` | Optional raw HTML response cap. `0` accepts large pages; AI context remains capped independently. |
| `MAX_DOM_CHARS` | No | `12000` | Maximum compact AI candidate context. |
| `AI_CONFIDENCE_THRESHOLD` | No | `0.65` | Lowest accepted AI confidence. |
| `DYNAMIC_FALLBACK_ENABLED` | No | `true` | Renders sparse JavaScript app shells in a browser before extraction. |
| `DYNAMIC_FALLBACK_MIN_TEXT_CHARS` | No | `300` | Static text threshold that triggers browser rendering. |
| `DYNAMIC_TIMEOUT_MILLISECONDS` | No | `30000` | Browser-render fallback timeout. |

Vite proxies `/api` to `VITE_API_PROXY_TARGET` during local development, so `VITE_API_BASE_URL` should remain empty. Set `VITE_API_BASE_URL` only when a deployed frontend needs a separate public API origin.

## Deploy to Railway

Railway builds the root `Dockerfile`, compiles the React frontend, installs Scrapling's Chromium runtime, and serves the frontend and FastAPI API from one public service. The container listens on Railway's injected `PORT`; `/api/health` is used as the deployment health check.

1. Push this repository to GitHub and create a Railway service from the repository.
2. Keep the service root directory set to the repository root. Railway will detect `railway.toml` and the root `Dockerfile` automatically.
3. Generate a public domain under **Settings → Networking** after the first successful deployment.

No server-side Gemini key is required because each user connects their own key in the browser and Scrapted sends it only in the `X-Gemini-API-Key` request header. Optional scraper settings from the backend environment-variable table can be added in Railway's **Variables** tab. Do not set `VITE_API_BASE_URL` for this single-service deployment—the frontend uses the same Railway origin for `/api` requests.

## Share a local demo

With the backend and frontend running, expose the frontend port with Cloudflare Quick Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:5173
```

Open the generated `https://…trycloudflare.com` URL. The Vite proxy keeps browser API calls on that same public origin and forwards them to your local FastAPI server. Use the actual Vite port if it differs from `5173`.

## API

`POST /api/scrape`

```json
{
  "url": "https://example.com/products",
  "query": "Find the price of the first product",
  "expected_selector": "#product-price"
}
```

Successful direct matches return `method: "direct_selector"`. AI paths return `ai_recovery` or `ai_discovery`, an actual verified selector, normalized value, HTML snippet, confidence, explanation, and a trace of executed stages.

When no result is confident enough, Scrapted returns HTTP 200 with `success: false` and `code: "ELEMENT_NOT_FOUND"`. Invalid requests, unsafe URLs, fetch failures, and unavailable AI services use the appropriate 4xx or 5xx response with a safe error message.

## Test and build

```bash
cd backend
source .venv/bin/activate
pytest

cd ../frontend
npm run build
```

## Limitations

- Scrapted renders sparse JavaScript app shells as a fallback, but does not automate authenticated flows, clicks, or other user interactions.
- Private, local, and internal network targets are intentionally rejected.
- Anti-bot protections and authenticated pages may still block scraping.
- There is no batching, scheduling, selector history, database, accounts, or analytics.
- AI fallback sends a compact representation of a public page’s candidate DOM elements to Gemini. Review Google’s free-tier data terms before using it with sensitive content.
