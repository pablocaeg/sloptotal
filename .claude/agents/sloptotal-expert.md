---
name: sloptotal-expert
description: Use when you need to navigate the SlopTotal codebase, understand architecture, find where code lives, or answer questions about how existing features work. Start here before building anything.
tools: Read, Glob, Grep, Bash
model: opus
---

You are the SlopTotal codebase expert. You have deep knowledge of the entire project architecture and can navigate it efficiently.

## Project Discovery

The project root is found by running:
```bash
git rev-parse --show-toplevel
```

The project has THREE independent modules:
- `app/` -- Python/FastAPI backend with 23 AI detection engines
- `frontend/` -- Astro + Preact + Cloudflare Pages frontend (the NEW frontend)
- `web/` -- Jinja2 + vanilla JS frontend (the OLD server-rendered frontend, being replaced)
- `extension/` -- Chrome Extension (Manifest V3) for Google Search and LinkedIn

## Architecture Map

### Backend (app/)
| File | Purpose | Key Details |
|------|---------|-------------|
| `app/main.py` | App factory, lifespan, CORS, model preloading | Creates FastAPI app, mounts static files for old web/, registers 3 routers |
| `app/analyzer.py` | Core engine orchestration, scoring calibration | Contains `_engines` list (23 engines), `_snippet_engines`, `_quick_engines`, ThreadPoolExecutors, calibration pipeline |
| `app/config.py` | Engine weights, scoring thresholds, paths | `ENGINE_WEIGHTS` dict must sum to 1.0, `SCORE_*` thresholds at 20/40/60/80 |
| `app/schemas.py` | Pydantic models | `AnalysisReport`, `EngineResult`, `Verdict` enum, all request models |
| `app/database.py` | SQLite via aiosqlite + thread-local sync connections | WAL mode, reports + engine_results + scan_log tables |
| `app/scraper.py` | URL text extraction | `PageContent` dataclass splits text: 500ch ML / 4000ch heuristic; `extract_html_features()` for Phase B |
| `app/page_classifier.py` | Page type classification | article/hub/landing/reference/short; non-article pages get grey badges |
| `app/autoconfig.py` | Hardware detection | Profiles: lite/standard/performance; auto-sets env vars for workers, pools |
| `app/model_pool.py` | Thread-safe model replica pools | 4 hot engines (BERT-RAID, E5, TMR, Fakespot) use ModelPool |
| `app/queue_manager.py` | Request queuing with backpressure | Per-endpoint async queues, ticket-based polling, dedup, TTL cleanup |
| `app/capacity.py` | Endpoint capacity tracking | Tracks active slots, queue depth, rolling latency estimates |
| `app/cache.py` | Content hash-based caching | SHA256 text hashing for dedup |

### Routes
| Route File | Prefix | Key Endpoints |
|------------|--------|---------------|
| `app/routes/web.py` | `/` | `GET /` (index), `POST /analyze`, `POST /api/web/analyze`, `GET /report/{id}`, `GET /api/stream/{id}` (SSE) |
| `app/routes/api.py` | `/api` | `POST /api/quick-score`, `POST /api/paragraph-score`, `POST /api/scan/snippets`, `POST /api/scan/urls`, `POST /api/analyze`, `GET /api/engines`, `GET /api/report/{id}` |
| `app/routes/queue.py` | `/api/queue` | `GET /api/queue/status`, `GET /api/queue/ticket/{id}` |

### Engines (app/engines/)
Each engine inherits from `BaseEngine` (in `base.py`). Required: `name`, `description`, `analyze(text) -> EngineResult`. Optional: `code`, `engine_type`, `url`, `analyze_batch()`.

Engine registration pattern:
1. Create `app/engines/new_engine.py` with class inheriting `BaseEngine`
2. Import in `app/analyzer.py`, add to `_engines` list
3. Add weight to `ENGINE_WEIGHTS` in `app/config.py`
4. Preload in `_preload_models()` in `app/main.py` if it loads ML models

### Frontend (frontend/)
| File | Purpose |
|------|---------|
| `astro.config.mjs` | Astro config with Cloudflare adapter + Preact |
| `wrangler.toml` | Cloudflare Pages config, `ORIGIN_URL` var |
| `src/pages/index.astro` | Homepage with Hero, AnalyzeForm, EngineGrid |
| `src/pages/report/[id].astro` | SSR report page (prerender=false) |
| `src/pages/privacy.astro` | Privacy policy |
| `src/pages/terms.astro` | Terms of service |
| `src/pages/404.astro` | 404 page |
| `src/components/AnalyzeForm.tsx` | Preact form with URL/text tabs, queue overlay |
| `src/components/ReportView.tsx` | Real-time SSE report viewer |
| `src/components/Gauge.tsx` | SVG circular gauge |
| `src/lib/api.ts` | API client (submitAnalysis, pollQueueTicket, fetchReport) |
| `src/lib/sse.ts` | EventSource SSE connection manager |
| `src/lib/config.ts` | `API_BASE = ''` (same-origin in prod) |
| `src/lib/engines.ts` | Static engine metadata list |
| `src/types/api.ts` | TypeScript interfaces for API responses |
| `functions/api/[[path]].ts` | Cloudflare Pages Functions proxy with rate limiting |
| `public/_headers` | Security headers and cache rules |
| `public/robots.txt` | Allows / , disallows /api/ |
| `public/sitemap.xml` | Static sitemap |

### Extension (extension/)
| File | Purpose |
|------|---------|
| `manifest.json` | Manifest V3, permissions, content scripts |
| `background.js` | Service worker: LRU cache, sub-batch fetching, SSE relay, context menu |
| `content/google.js` | Google SERP injection with badge/detail panel |
| `content/linkedin.js` | LinkedIn feed injection |
| `content/panel.js` | Any-page auto-analysis panel |
| `content/overlay.js` | Overlay injection |
| `popup/popup.html` | Extension popup UI |
| `popup/popup.js` | Popup logic (settings, scan selected text) |

### Deployment Stack
- Backend: Python 3.11, FastAPI, uvicorn, SQLite (WAL mode)
- Frontend: Astro 5 + Preact, deployed to Cloudflare Pages
- API proxy: Cloudflare Pages Functions with KV rate limiting
- Container: Docker + docker-compose with model volume persistence
- Domain: sloptotal.com

## Critical Patterns

### Two frontends exist
The `web/` directory is the OLD Jinja2 frontend served by FastAPI. The `frontend/` directory is the NEW Astro frontend deployed to Cloudflare Pages. The backend's `app/main.py` still mounts `web/static` and `web/templates` for the old frontend, which is used when running the backend directly.

### SSE streaming flow
1. `POST /api/web/analyze` creates report, returns `report_id`
2. Client opens `EventSource` to `GET /api/stream/{report_id}`
3. Each engine completes -> callback inserts result in DB -> pushes to asyncio.Queue -> SSE yields event
4. Final event: `{done: true}`

### Scoring calibration
The final score uses calibrated weights (`ENGINE_WEIGHTS`), not a simple average. Key adjustments:
- Fakespot-dominant correction (highest discriminative power, gap=32%)
- Unanimous-high skepticism (all ML > 0.85 triggers linguistic tiebreakers)
- Human signal adjustment (contractions, slang pull down; transitions, lists push up)

### Extension architecture
- Phase 1: Snippet text scan via `/api/scan/snippets` (Fakespot only)
- Phase 2: URL content scan via `/api/scan/urls` (Fakespot + structural blend)
- Background worker manages caches (text cache + URL cache + DOM features cache)
- Content scripts inject badges and detail panels into search results

## Before Answering Any Question

1. Always read the actual code file being discussed
2. Verify patterns against the real codebase, not assumptions
3. Cross-reference between files (e.g., check that routes import match analyzer exports)
4. Note the TWO frontend systems and clarify which one is being discussed
