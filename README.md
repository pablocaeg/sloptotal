# SlopTotal

[![CI](https://github.com/pablocaeg/sloptotal/actions/workflows/ci.yml/badge.svg)](https://github.com/pablocaeg/sloptotal/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-sloptotal.com-blue)](https://sloptotal.com)

**VirusTotal for AI slop detection.** Scan any text or URL with 23 independent detection engines running entirely on your hardware. No data sent to third parties.

## What it does

SlopTotal runs 23 AI detection engines in parallel -- neural classifiers, statistical tests, and linguistic heuristics -- and produces a calibrated forensic score. Results stream in real-time as each engine completes.

**Live demo:** [sloptotal.com](https://sloptotal.com)

## Quick Start

```bash
# Clone and install
git clone https://github.com/pablocaeg/sloptotal.git
cd sloptotal
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start (auto-detects hardware, downloads models on first run)
./start.sh
# or manually:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

### Docker

```bash
docker compose up
```

## Architecture

```
sloptotal/
├── app/                    # Backend (Python/FastAPI)
│   ├── main.py             # App factory, lifespan, middleware
│   ├── routes/
│   │   ├── web.py          # Web page routes (/, /report, /analyze, SSE)
│   │   ├── api.py          # JSON API (/api/quick-score, /api/analyze, etc.)
│   │   └── queue.py        # Queue status & ticket polling
│   ├── analyzer.py         # Core analysis orchestration & scoring
│   ├── engines/            # 23 detection engines
│   │   ├── base.py         # BaseEngine ABC
│   │   └── ...             # One file per engine
│   ├── config.py           # Configuration & engine weights
│   ├── schemas.py          # Pydantic models
│   ├── database.py         # SQLite async storage
│   ├── cache.py            # Content hashing & caching
│   ├── scraper.py          # URL content extraction
│   ├── autoconfig.py       # Hardware detection & profiling
│   ├── model_pool.py       # Thread-safe model replica pools
│   └── queue_manager.py    # Request queuing & backpressure
├── web/                    # Web Frontend
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS, JS, images
├── extension/              # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js
│   ├── popup/
│   └── content/
└── tests/                  # Evaluation scripts
```

## API Endpoints

| Endpoint | Method | Description | Latency |
|----------|--------|-------------|---------|
| `/api/quick-score` | POST | 6 engines (fast) | ~100-500ms |
| `/api/paragraph-score` | POST | Per-paragraph heat map | ~1-3s |
| `/api/scan/snippets` | POST | Batch scan (1-30 snippets) | ~500ms |
| `/api/analyze` | POST | Full 23-engine analysis | ~3-8s |
| `/api/engines` | GET | Engine metadata | instant |
| `/api/recent` | GET | Recent reports | instant |
| `/api/report/{id}` | GET | Full report data | instant |
| `/api/queue/status` | GET | Queue capacity | instant |

### Quick Score Example

```bash
curl -X POST http://localhost:8000/api/quick-score \
  -H "Content-Type: application/json" \
  -d '{"text": "Your text to analyze here..."}'
```

Response:
```json
{
  "score": 72.3,
  "verdict": "ai",
  "confidence": "high",
  "engines": [...],
  "elapsed_ms": 340.2
}
```

## Detection Engines

### Neural Classifiers
| Engine | Model | Notes |
|--------|-------|-------|
| TMR Detector | RoBERTa-base | RAID-trained, 97.3% accuracy |
| ReMoDetect | DeBERTa | Targets RLHF-aligned LLMs |
| Fakespot | RoBERTa-base | APOLLO system, best discriminator |
| BERT-tiny RAID | BERT-tiny (4.4M) | Ultra-fast inference |
| Desklib DeBERTa | DeBERTa-v3-large | Trained on GPT-4/Claude |
| SuperAnnotate | RoBERTa-large | Low false-positive optimized |
| OpenAI Detector | RoBERTa | Original OpenAI detector |
| ChatGPT Detector | RoBERTa | ChatGPT-specific |
| E5-Small | E5 + LoRA | 33M params, embedding-based |

### Statistical Methods
| Engine | Method |
|--------|--------|
| Binoculars | Cross-entropy ratio between two LMs |
| Fast-DetectGPT | Conditional probability curvature |
| Perplexity | GPT-2 perplexity scoring |
| Cross-Perplexity | Multi-model perplexity comparison |
| GLTR | Token rank distribution |
| Log-Rank | Average log-rank under GPT-2 |
| DivEye | Surprisal diversity |

### Linguistic Heuristics
| Engine | Signal |
|--------|--------|
| Burstiness | Per-sentence perplexity variance |
| Linguistic Markers | AI-preferred phrases ("delve", "tapestry"...) |
| Structural | Em-dash usage, sentence uniformity |
| Vocabulary | Type-token ratio, hapax legomena |
| Formulaic | Cliche openings/closings |
| Readability | Cross-paragraph consistency |
| Sentiment | Hedging & forced balance |

## Scoring

The final score is **calibrated**, not a simple average. Key principles:

1. **Fakespot-dominant weighting** -- Fakespot has the largest human/AI gap (32%) and anchors the calibration
2. **Unanimous-high skepticism** -- When all ML classifiers agree on very high scores, linguistic/formulaic engines act as tiebreakers (catches the "formal human text" false positive)
3. **Human signal adjustment** -- Contractions, slang, first-person voice pull the score down; AI transitions and list patterns push it up

## Hardware Requirements

| Profile | RAM | CPU | GPU | Notes |
|---------|-----|-----|-----|-------|
| Lite | 4GB | 2 cores | None | Runs all engines, slower |
| Standard | 8GB | 4 cores | None | Recommended |
| Performance | 16GB+ | 6+ cores | CUDA | Fastest, GPU-accelerated |

Hardware is auto-detected on startup. Override with environment variables:

```bash
SLOPTOTAL_TORCH_THREADS=4
SLOPTOTAL_FULL_WORKERS=6
SLOPTOTAL_SNIPPET_WORKERS=4
SLOPTOTAL_MAX_CONCURRENT_FULL=3
```

## Chrome Extension

The SlopTotal Chrome extension is maintained as a **separate open-source repository**:

**[pablocaeg/sloptotal-extension](https://github.com/pablocaeg/sloptotal-extension)**

Features:
- Scans Google search results inline with AI probability badges
- Scans LinkedIn feed posts with AI detection
- Quick-score popup for any page or selected text
- Right-click context menu integration
- Configurable API — point at any SlopTotal backend

Install from the [extension repo](https://github.com/pablocaeg/sloptotal-extension) or load `extension/` as an unpacked extension for development.

## AI Agents

This project ships with **11 specialized AI agents** that can autonomously navigate, build, test, review, and ship contributions. They work with any AI coding assistant — Claude Code, Cursor, GitHub Copilot, ChatGPT, Gemini, Windsurf, or programmatic API calls. Anyone who clones this repo gets access to them automatically.

```
sloptotal-expert          # Understand the codebase
sloptotal-completionist   # Find what's missing or broken
sloptotal-feature-builder # Build new engines, endpoints, pages
sloptotal-test-writer     # Create tests with proper patterns
sloptotal-reviewer        # Code review before PR
sloptotal-optimizer       # Performance, SEO, accessibility
sloptotal-deployer        # CI/CD and deployment
sloptotal-open-source     # GitHub templates and discoverability
sloptotal-extension-extractor  # Extract extension to its own repo
sloptotal-pr-creator      # Git workflow and PR creation
sloptotal-contribute      # Master orchestrator for end-to-end workflows
```

See [docs/ai-agents/](docs/ai-agents/) for full documentation, workflow pipelines, and usage examples.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to add new detection engines.

- [Bug Report](https://github.com/pablocaeg/sloptotal/issues/new?template=bug_report.yml)
- [Feature Request](https://github.com/pablocaeg/sloptotal/issues/new?template=feature_request.yml)
- [Propose a New Engine](https://github.com/pablocaeg/sloptotal/issues/new?template=new_engine.yml)

## License

MIT
