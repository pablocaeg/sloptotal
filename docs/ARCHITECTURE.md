# SlopTotal Architecture

## Layout

```
sloptotal/
├── app/          Backend (Python/FastAPI)
├── web/          Web UI (Jinja2 + vanilla JS), served by the backend
├── tests/        Unit tests and the tests/eval/ accuracy harness
└── scripts/      End-to-end smoke test, model drift check
```

The Chrome extension lives in its own repository,
[pablocaeg/sloptotal-extension](https://github.com/pablocaeg/sloptotal-extension),
and talks to the JSON API.

### Backend (`app/`)

FastAPI application with hardware-aware auto-configuration.

**Entry point:** `app/main.py` -- app factory, lifespan, CORS, static mounts, router includes (~120 lines).

**Routes:**
- `app/routes/web.py` -- HTML page routes (`/`, `/analyze`, `/report/{id}`, `/api/stream/{id}`, `/api/web/analyze`)
- `app/routes/api.py` -- JSON API routes (`/api/quick-score`, `/api/paragraph-score`, `/api/scan/snippets`, `/api/analyze`, `/api/engines`, etc.)
- `app/routes/queue.py` -- Queue management (`/api/queue/status`, `/api/queue/ticket/{id}`)

**Core:**
- `app/analyzer.py` -- Engine orchestration, batch inference
- `app/calibration.py` -- The overall score, its confidence and language support, from the fits in `app/calibration.json`
- `app/engines/` -- 23 detection engines, each inheriting from `BaseEngine`
- `app/config.py` -- Engine weights, scoring thresholds, paths
- `app/schemas.py` -- Pydantic models for requests/responses
- `app/autoconfig.py` -- Hardware detection (CPU/GPU/RAM), profile selection (lite/standard/performance)
- `app/model_pool.py` -- Thread-safe model replica pools for hot engines
- `app/queue_manager.py` -- Request queuing with backpressure
- `app/database.py` -- SQLite async storage for reports
- `app/cache.py` -- Content hash-based caching
- `app/scraper.py` -- URL fetching (rejects private/metadata addresses on every redirect hop) and main-content extraction
- `app/site_fingerprints.py` -- AI app builder detection (Lovable, v0, Bolt, Base44, Replit, Same, Emergent); see [docs/SITE_FINGERPRINTS.md](SITE_FINGERPRINTS.md)
- `app/documents.py` -- Text extraction from uploaded PDF / DOCX / TXT

### Web Frontend (`web/`)

Server-rendered Jinja2 templates with vanilla JavaScript.

- `web/templates/base.html` -- Layout, header, ticker, footer
- `web/templates/index.html` -- Homepage with dynamic engine grid
- `web/templates/report.html` -- Live report page
- `web/static/css/style.css` -- All styles (forensic lab aesthetic)
- `web/static/js/app.js` -- Tab switching, queue-aware form submission, ticker
- `web/static/js/report.js` -- SSE streaming, gauge animation, engine row updates

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
- Every model load holds `model_pool.LOAD_LOCK`. transformers' `from_pretrained` is not thread-safe across models; concurrent loads (preloader plus first request) have left GPT-2's tied head randomly initialised. Lazy loaders use double-checked locking and publish the model only after the tokenizer is set and `eval()` has run.

### Scoring Calibration

The score is produced by `app/calibration.py`. Parameters live in `app/calibration.json` and are never edited by hand; they are fitted by `tests/eval/slopbench/fit.py` (English) and `fit_multilingual.py`.

- **Logistic model** -- a weighted sum of engine logits with non-negative weights, mapped to 0-100 by piecewise-linear knots calibrated so band edges match a measured share of human text.
- **Short-text adjustment** -- English texts under `SHORT_TEXT_WORDS = 80` are pulled toward a neutral score by `words / (words + k)`; other spaced languages use `short_alpha`.
- **Per-language support** -- each language carries an offset and a support status: `supported`, `experimental`, or `unsupported`. Unsupported languages are scored but never above low confidence.
- **Confidence** -- low for short texts, scores in `UNCERTAIN` (35-65), or unsupported languages; at most medium for experimental languages; high only outside `CONFIDENT` (15/80).

The quick path has its own calibration, fitted by `tests/eval/slopbench/fit_quick.py`.

Verdict bands (`SCORE_CLEAN` ... `SCORE_LIKELY_AI`) live only in `config.py`; the report page receives them from the template.

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

### Site check
```
Browser / client POST /api/scan/site {url}
    → fetch_page(): guarded fetch, returns HTML, headers, final URL
    → detect_builders(): host, header and HTML fingerprints per builder
    → optional quick text score of the extracted main content
    → {site: {builders, generator, verdict}, text: {...} | null}
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
