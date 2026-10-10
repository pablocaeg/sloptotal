# Contributing to SlopTotal

Thank you for your interest in contributing! SlopTotal is open source and welcomes contributions of all kinds.

## Ways to Contribute

### Good First Issues

The [good first issues](https://github.com/pablocaeg/sloptotal/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are small, self-contained tasks. Each one names the files to change and how to test the result. Comment on the one you want and it will be assigned to you.

### Engine Contributions

Adding new AI detection engines is the most impactful contribution. See [How to Add a New Engine](#how-to-add-a-new-engine) below.

### Other Contributions

- Performance optimizations
- Web UI improvements
- CI/CD and infrastructure
- Security hardening

## Development Setup

**Requires Python 3.10+** (3.11 recommended).

```bash
git clone https://github.com/pablocaeg/sloptotal.git
cd sloptotal
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --port 8000 --reload
```

Install git hooks so ruff runs on `app`, `tests` and `scripts` before you push:
`pip install pre-commit && pre-commit install`

Models (~2 GB) download on first run. Use `SLOPTOTAL_PROFILE=lite` on small
machines. The web UI lives in `web/` (Jinja2 templates and vanilla JS, no build
step). The Chrome extension has its own repository:
[pablocaeg/sloptotal-extension](https://github.com/pablocaeg/sloptotal-extension).

### Tests

```bash
pytest -q                        # unit tests: seconds, no model downloads
ruff check app tests scripts
ruff format --check app tests scripts
python scripts/smoke_test.py     # end to end, against a running server
```

The smoke test hits every route with real inference and fails if any engine
reports a load error. Run it after touching engines, dependencies or the
Dockerfile.

### Measuring accuracy

`tests/eval/` holds the corpus builders and the harness behind every number in
the README. Build the corpora, run them against your instance, and compare:

```bash
cd tests/eval
python build_classics.py            # 26 pre-1920 passages (human by construction)
python build_multidomain.py         # RAID news / books / poetry / abstracts
SLOPTOTAL_API=http://localhost:8000/api/analyze python run_any.py corpus_classics.json results.json
```

Any change to an engine, a weight or the calibration needs before/after numbers
on both corpora in the PR. `tests/eval/candidate_models.py` scores new Hugging
Face detectors on their own, to decide whether they are worth adding.

## How to Add a New Engine

1. **Create** `app/engines/your_engine.py` inheriting from `BaseEngine` (`app/engines/base.py`)
2. **Implement** `name`, `description`, `code`, `engine_type`, and `analyze(text) -> EngineResult`
3. **Register** it in `_engines` in `app/analyzer.py`
4. **Weight** it in `ENGINE_WEIGHTS` in `app/config.py` (weights must sum to 1.0)
5. **Load models under `model_pool.LOAD_LOCK`** and add the loader to `_preload_models()` in `app/main.py`
6. **Measure** it on both corpora and include AUC and literary bias in the PR

See existing engines for reference:
- Neural: `app/engines/classifier_fakespot.py`
- Statistical: `app/engines/perplexity.py`
- Linguistic: `app/engines/linguistic.py`

## Pull Request Process

1. Fork the repo and create a feature branch (`feat/`, `fix/`, `docs/`, etc.)
2. Make your changes with tests where applicable
3. Run lint and tests locally
4. Submit a PR using the provided template
5. Address review feedback

### Commit Style

Use conventional commits:
```
feat: add new burstiness variant engine
fix: handle empty text in perplexity engine
docs: update API endpoint documentation
```

## Architecture Overview

```
app/           FastAPI backend: 23 engines, ensemble, site fingerprints, API
web/           Web UI served by the backend (Jinja2 + vanilla JS)
tests/         Unit tests; tests/eval/ holds the accuracy harness
scripts/       End-to-end smoke test and model drift check
benchmarks/    Speed and load scripts
```

See [ARCHITECTURE.md](../docs/ARCHITECTURE.md) for internals and [AGENTS.md](../AGENTS.md)
for the short list of rules that are easy to break.

## Code Style

- **Python**: type hints, absolute imports (`from app.`), logging via `logging.getLogger("sloptotal.*")`, formatted with ruff
- **Web UI**: vanilla JS and CSS custom properties from `style.css`; no frameworks or build step

## Important Rules

- All detection runs locally. Do NOT add external API calls to engines.
- ENGINE_WEIGHTS must always sum to 1.0.
- Do NOT change engine `analyze()` signatures.
- Do NOT modify scoring calibration without running full evaluation.
- Do NOT call `from_pretrained()` outside `model_pool.LOAD_LOCK`.
- Do NOT commit secrets, database files, or model weights.
