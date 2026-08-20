# scrapted_

> **Tell us what you want. We'll find where the DOM hid it.**

Scrapted is an AI-powered web scraping agent that takes a public URL and a plain-English request — *"find the price of the first product"* — and returns the exact value along with its verified CSS selector. It does this by reading the page DOM, stripping noise, and using Google Gemini to semantically match the element you described.

---

## About the Project

Most scrapers break the moment a website changes its markup. Scrapted is different: it understands *what* you're looking for, not just *where* it used to be.

**What it does:**

- **Direct selector match** — if you supply an expected CSS selector and the element is still there, Scrapted resolves it instantly without touching the AI.
- **AI recovery** — if your old selector is broken, Scrapted finds the replacement automatically and reports the confidence score.
- **AI discovery** — if you have no selector at all, describe the element in plain English and Scrapted locates it from scratch.
- **Live inspection UI** — watch every decision the agent makes in real time: fetching, reading markup, rewriting the DOM, and matching your request — all visualised step by step.
- **Streaming responses** — results arrive over a Server-Sent Events stream so the UI updates as work progresses, not just when it's done.
- **Privacy-first** — your Gemini API key is kept only in the current browser session and is never stored server-side.

---

## Tech Stack

### Backend

| Layer | Technology |
|---|---|
| API framework | [FastAPI](https://fastapi.tiangolo.com/) ≥ 0.115 |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) with `uvloop` + `httptools` |
| Web scraping | [Scrapling](https://github.com/D4Vinci/Scrapling) 0.4.11 (fetchers extra) |
| HTTP client | [httpx](https://www.python-httpx.org/) |
| Configuration | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| AI model | Google Gemini (via REST, model configurable) |
| Language | Python 3.12+ |

### Frontend

| Layer | Technology |
|---|---|
| Framework | [React](https://react.dev/) 19 |
| Language | TypeScript |
| Build tool | [Vite](https://vitejs.dev/) |
| Styling | Vanilla CSS (custom design system, no frameworks) |
| Transport | `EventSource` / SSE for streaming |

---

## Architecture

```
web_scraper/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py        # FastAPI router — all /api/* endpoints
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings (env vars)
│   │   │   └── errors.py        # AppError domain exception
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic request / response models
│   │   ├── services/
│   │   │   ├── ai.py            # Gemini API client & key validation
│   │   │   └── scraper.py       # Scraping orchestration logic
│   │   └── main.py              # App factory; mounts frontend dist in prod
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.tsx              # Entire UI — form, live inspector, results
    │   ├── services/api.ts      # SSE stream client & REST helpers
    │   ├── types/               # Shared TypeScript types
    │   └── styles.css           # Full custom design system
    ├── index.html
    └── vite.config.ts
```

### Request flow

```
Browser
  │
  │  POST /api/scrape/stream   (SSE)
  ▼
FastAPI (uvicorn)
  │
  ├─► ScrapingService
  │     ├─ Fetches page HTML via Scrapling
  │     ├─ Streams "source_ready" event → UI shows page source panel
  │     ├─ Compresses DOM (strips scripts, styles, hidden nodes)
  │     ├─ Streams "compressed_dom" event → UI shows agent draft panel
  │     └─ Calls GeminiAIService with compact DOM + user query
  │
  └─► GeminiAIService
        ├─ Sends DOM context + query to Gemini REST API
        ├─ Parses selector + confidence from model response
        └─ Verifies selector against the live page
  │
  ▼  Streams "result" event
Browser
  └─ Renders matched value, selector, confidence, and matched HTML
```

### Scraping methods

| Method | When it runs |
|---|---|
| `direct_selector` | Expected selector is provided and element is found immediately |
| `ai_recovery` | Expected selector is provided but the element has moved — Gemini finds the new one |
| `ai_discovery` | No selector provided — Gemini locates the element purely from the query |

### Production deployment

When `frontend/dist/` exists (after `npm run build`), the FastAPI app automatically mounts it at `/`, serving the full SPA from the same origin as the API with no separate static server needed.

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+ (for the frontend)
- A [Google Gemini API key](https://ai.google.dev/gemini-api/docs/api-key)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your GEMINI_API_KEY
uvicorn app.main:app --reload
# API running at http://localhost:8000
# Docs at      http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# UI running at http://localhost:5173
```

### Environment variables (backend)

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model name |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed CORS origins |
| `SCRAPE_TIMEOUT_SECONDS` | `10` | Page fetch timeout |
| `MAX_RESPONSE_BYTES` | `0` (unlimited) | Max page size to accept |
| `MAX_DOM_CHARS` | `12000` | Max compact DOM characters sent to Gemini |
| `AI_CONFIDENCE_THRESHOLD` | `0.65` | Minimum match confidence to accept |
| `DYNAMIC_FALLBACK_ENABLED` | `true` | Use headless browser if static fetch is thin |
| `DYNAMIC_TIMEOUT_MILLISECONDS` | `30000` | Headless browser timeout |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/ai/validate` | Validate a Gemini API key |
| `POST` | `/api/scrape` | Scrape a URL (returns full result) |
| `POST` | `/api/scrape/stream` | Scrape a URL with SSE progress events |

All endpoints except `/api/health` require the `X-Gemini-API-Key` header.
