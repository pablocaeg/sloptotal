# SlopTotal Architecture

## Three-Module Design

SlopTotal is organized into three independent modules:

```
sloptotal/
├── app/          Backend (Python/FastAPI)
├── web/          Web Frontend (Jinja2 + vanilla JS)
└── extension/    Chrome Extension (Manifest V3)
```

### Backend (`app/`)

FastAPI application with hardware-aware auto-configuration.

**Entry point:** `app/main.py` -- app factory, lifespan, CORS, static mounts, router includes (~120 lines).

**Routes:**
- `app/routes/web.py` -- HTML page routes (`/`, `/analyze`, `/report/{id}`, `/api/stream/{id}`, `/api/web/analyze`)
- `app/routes/api.py` -- JSON API routes (`/api/quick-score`, `/api/paragraph-score`, `/api/scan/snippets`, `/api/analyze`, `/api/engines`, etc.)
- `app/routes/queue.py` -- Queue management (`/api/queue/status`, `/api/queue/ticket/{id}`)

**Core:**
- `app/analyzer.py` -- Engine orchestration, scoring calibration, batch inference
- `app/engines/` -- 23 detection engines, each inheriting from `BaseEngine`
- `app/config.py` -- Engine weights, scoring thresholds, paths
- `app/schemas.py` -- Pydantic models for requests/responses
- `app/autoconfig.py` -- Hardware detection (CPU/GPU/RAM), profile selection (lite/standard/performance)
- `app/model_pool.py` -- Thread-safe model replica pools for hot engines
- `app/queue_manager.py` -- Request queuing with backpressure
- `app/database.py` -- SQLite async storage for reports
- `app/cache.py` -- Content hash-based caching
- `app/scraper.py` -- URL content extraction

### Web Frontend (`web/`)

Server-rendered Jinja2 templates with vanilla JavaScript.

- `web/templates/base.html` -- Layout, header, ticker, footer
- `web/templates/index.html` -- Homepage with dynamic engine grid
- `web/templates/report.html` -- Live report page
- `web/static/css/style.css` -- All styles (forensic lab aesthetic)
- `web/static/js/app.js` -- Tab switching, queue-aware form submission, ticker
- `web/static/js/report.js` -- SSE streaming, gauge animation, engine row updates

### Chrome Extension (`extension/`)

Manifest V3 extension for inline AI detection on Google and LinkedIn.

- `extension/background.js` -- Service worker with LRU cache (500 entries, 1hr TTL)
- `extension/content/google.js` -- SERP injection using `.g` and `.VwiC3b` selectors
- `extension/content/linkedin.js` -- Feed injection on `.feed-shared-update-v2`
- `extension/popup/` -- Settings UI with API URL, toggles, recent scans

---

## Engine Architecture

Each engine inherits from `BaseEngine` and provides:
- `name`, `description` -- Display metadata
- `code` -- 2-letter short code (e.g. "FS" for Fakespot)
- `engine_type` -- Category: neural, statistical, linguistic, embedding, classifier
- `url` -- Link to model/paper
- `analyze(text)` -- Returns `EngineResult` with score, verdict, details
- `analyze_batch(texts)` -- (Optional) Batch inference for snippet scanning

### Concurrency Model

```
Incoming request
    ├── Snippet endpoint ──→ _snippet_executor (4 workers)
    ├── Quick-score      ──→ _snippet_executor (shared)
    └── Full analysis    ──→ _full_executor (N workers, N = usable cores)
```

- Semaphore guards prevent overload (`_snippet_semaphore`, `_full_semaphore`)
- `QueueManager` provides request queuing with ticket-based polling for web clients
- 4 "hot" engines (BERT-RAID, E5, TMR, Fakespot) use `ModelPool` for thread-safe replica access

### Scoring Calibration

The final score is **not** a simple average. The calibration pipeline:

1. **Weighted baseline** -- ENGINE_WEIGHTS in config.py (based on MAGE + RAID evaluation)
2. **Fakespot-dominant correction** -- Fakespot has the largest human/AI discrimination gap (32%)
3. **Unanimous-high skepticism** -- When all ML classifiers score >0.85, linguistic/formulaic engines differentiate formal human text from AI
4. **No-markers penalty** -- High ML score + zero AI linguistic markers = likely false positive
5. **Human signal adjustment** -- Contractions, slang, first-person voice pull score down

---

## Data Flow

### Full Analysis (Web)
```
Browser POST /api/web/analyze
    → QueueManager checks capacity
    → start_analysis() creates report in SQLite
    → 23 engines run in parallel via _full_executor
    → Each engine callback: insert result → recalculate score → push to asyncio.Queue
    → Browser receives report_id, opens /report/{id}
    → EventSource /api/stream/{id} yields SSE events as engines complete
    → Final SSE event: {done: true}
```

### Snippet Scan (Chrome Extension)
```
Extension POST /api/scan/snippets [{id, text, url}, ...]
    → QueueManager checks capacity
    → 3 engines (BERT-RAID, E5, Fakespot) run batched inference
    → Each engine: single forward pass for all N texts
    → Fakespot-anchored calibration per snippet
    → Return [{id, score, indicator, confidence}, ...]
```
