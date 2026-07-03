# Contributing to SlopTotal

Thank you for your interest in contributing! SlopTotal is open source and welcomes contributions of all kinds.

## Ways to Contribute

### Good First Issues

- Adding linguistic patterns to existing heuristic engines
- Improving test coverage
- Documentation improvements
- Accessibility fixes
- Bug reports with reproduction steps

### Engine Contributions

Adding new AI detection engines is the most impactful contribution. See [How to Add a New Engine](#how-to-add-a-new-engine) below.

### Other Contributions

- Performance optimizations
- Frontend improvements
- Chrome extension features
- CI/CD and infrastructure
- Security hardening

## Development Setup

### Backend

**Requires Python 3.10+** (3.11 recommended).

```bash
git clone https://github.com/pablocaeg/sloptotal.git
cd sloptotal
python3.11 -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Start with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Models (~2 GB) download automatically on first run. Use `SLOPTOTAL_PROFILE=lite` for low-resource machines, or `SLOPTOTAL_PROFILE=performance` with extra workers on high-RAM CPU servers (see README).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on Astro + Preact and deploys to Cloudflare Pages.

### Chrome Extension

Load `extension/` as an unpacked extension in Chrome (`chrome://extensions` > Developer mode > Load unpacked). It connects to `localhost:8000` by default.

### Running Tests

```bash
# Unit tests
pytest tests/ -x -v -k "not slow"

# Evaluation benchmarks (requires models loaded)
python tests/eval_dataset.py
python tests/eval_hard.py
```

### Linting

```bash
pip install ruff
ruff check app/
ruff format --check app/
```

## How to Add a New Engine

1. **Create** `app/engines/your_engine.py` inheriting from `BaseEngine` (`app/engines/base.py`)
2. **Implement** `name`, `description`, `code`, `engine_type`, and `analyze(text) -> EngineResult`
3. **Register** in `app/analyzer.py` by adding to the `_engines` list
4. **Add weight** to `ENGINE_WEIGHTS` in `app/config.py` (all weights must sum to 1.0)
5. **Add metadata** to `frontend/src/lib/engines.ts`
6. **Preload** in `app/main.py` `_preload_models()` if it loads ML models
7. **Run evaluation**: `python tests/eval_dataset.py`

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
app/           Python/FastAPI backend with 23 detection engines
frontend/      Astro + Preact frontend (Cloudflare Pages)
web/           Legacy Jinja2 frontend (served by backend directly)
extension/     Chrome Extension (Manifest V3)
tests/         Evaluation benchmarks and unit tests
docs/          Architecture docs and AI agent documentation
.claude/       AI agents for autonomous contribution (works with any AI tool)
```

For detailed architecture, see [docs/ARCHITECTURE_NEXT.md](docs/ARCHITECTURE_NEXT.md).

## AI Agents

This project includes 11 AI agents that can help you contribute. They work with any AI coding assistant — just load the agent prompt from `.claude/agents/` into your tool of choice. See [docs/ai-agents/](docs/ai-agents/) for details.

## Code Style

- **Python**: Type hints, absolute imports (`from app.`), logging via `logging.getLogger("sloptotal.*")`
- **Frontend**: Preact (not React), CSS custom properties from `global.css`
- **Extension**: Vanilla JS, zero dependencies, console.log with `[BG]`/`[G]` prefixes

## Important Rules

- All detection runs locally. Do NOT add external API calls to engines.
- ENGINE_WEIGHTS must always sum to 1.0.
- Do NOT change engine `analyze()` signatures.
- Do NOT modify scoring calibration without running full evaluation.
- Do NOT commit secrets, database files, or model weights.
