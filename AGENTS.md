# AGENTS.md

Guidance for AI coding assistants (Claude Code, Cursor, Codex, Copilot, ...) and
for humans who like a short brief. Read this before changing code.

## What this is

SlopTotal is a self-hosted AI text detector: 23 engines (neural classifiers,
statistical tests on GPT-2, linguistic heuristics) run in parallel and a
calibrated ensemble turns them into one score. It also checks whether a website
was built with an AI app builder. FastAPI backend, Jinja2 + vanilla JS UI, SQLite.
Everything runs locally on CPU; no engine may call an external API.

## Layout

```
app/main.py              app factory, lifespan, model preload
app/analyzer.py          engine orchestration and the calibrated ensemble
app/config.py            ENGINE_WEIGHTS, verdict bands (SCORE_*), paths
app/engines/             one file per engine, all subclass BaseEngine
app/model_pool.py        ModelPool replicas and LOAD_LOCK (see below)
app/site_fingerprints.py AI app builder detection (Lovable, v0, Bolt, ...)
app/scraper.py           URL fetching (private-address guard) and extraction
app/documents.py         PDF / DOCX / text upload extraction
app/routes/              web.py (pages, SSE), api.py (JSON), queue.py
web/                     templates and static assets for the UI
tests/                   fast unit tests (no models, no network)
tests/eval/              accuracy harness and published corpora results
scripts/smoke_test.py    end-to-end check against a running server
benchmarks/              speed and load scripts
```

## Commands

```bash
pip install -r requirements-dev.txt
pytest -q                                  # ~7 s, no downloads
ruff check app tests scripts && ruff format --check app tests scripts
uvicorn app.main:app --port 8000           # first run downloads ~9 GB of models
python scripts/smoke_test.py               # every route, all 23 engines, live
```

## Rules that are not obvious from the code

- **Every `from_pretrained()` must hold `model_pool.LOAD_LOCK`.** transformers
  loading is not thread-safe across models; concurrent loads have produced a
  randomly initialised GPT-2 head. Lazy loaders use double-checked locking and
  publish the model last (after the tokenizer is set and `eval()` has run).
- **Scores are measured, not tuned by feel.** Engine weights, verdict bands and
  calibration steps come from `tests/eval/`. If you change an engine, a weight
  or the calibration, re-run the corpora (see `tests/eval/FINDINGS.md`) and
  report before/after numbers in the PR. Include the Gutenberg classics set: a
  high score there is a false positive by construction.
- **Upgrading torch/transformers can move scores.** Re-run the classics corpus
  and compare per-engine scores before bumping them (Dependabot ignores them).
- **Verdict bands live only in `config.py`.** The report page receives them from
  the template; do not hardcode thresholds in JS or Python elsewhere.
- **Site fingerprints report evidence, not probabilities.** Only add a signal
  after confirming it on live deployments or the builder's own templates, and
  add a fixture to `tests/test_site_fingerprints.py`.
- **URL fetching goes through `scraper._fetch`**, which blocks private and
  metadata addresses on every redirect hop.
- ENGINE_WEIGHTS must sum to 1.0. Do not change `analyze()` signatures.

## Adding an engine

1. `app/engines/<name>.py`: subclass `BaseEngine`, implement `name`,
   `description`, `code`, `engine_type`, `analyze(text) -> EngineResult`.
2. Register it in `_engines` in `app/analyzer.py`; add its weight to
   `ENGINE_WEIGHTS` and re-normalise.
3. If it loads a model, load under `LOAD_LOCK` and add it to
   `_preload_models()` in `app/main.py`.
4. Measure it with `tests/eval/` and put the AUC and literary bias in the PR.

## Conventions

Python 3.10+, type hints, absolute imports (`from app...`), loggers named
`sloptotal.*`. Commit messages explain *why*, in plain prose. Keep the UI
dependency-free (no frameworks, no build step).
