# SlopTotal

[![CI](https://github.com/pablocaeg/sloptotal/actions/workflows/ci.yml/badge.svg)](https://github.com/pablocaeg/sloptotal/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-sloptotal.com-blue)](https://sloptotal.com)

**VirusTotal for AI slop detection.** Scan any text or URL with 23 independent detection engines running entirely on your hardware. No data sent to third parties.

## What it does

SlopTotal runs 23 AI detection engines in parallel -- neural classifiers, statistical tests, and linguistic heuristics -- and produces a calibrated forensic score. Results stream in real-time as each engine completes.

**Live demo:** [sloptotal.com](https://sloptotal.com) — or read the [per-engine scores](https://sloptotal.com/engines/) and [what the measurements show](https://sloptotal.com/detect/ai-detector-benchmark/).

## Measured accuracy

Most detectors publish an accuracy figure without saying what it was measured on.
These numbers, the harness that produced them and the raw per-sample results are
all in [tests/eval/](tests/eval/).

Two corpora, deliberately:

| Corpus | What | Size |
|---|---|---|
| Multi-domain | RAID: news, book prose, poetry, academic abstracts. AI from GPT-4, ChatGPT, Llama, Mistral, Cohere, GPT-3 | 110 (40 human, 70 AI) |
| Literary control | Project Gutenberg prose published 1532-1915 -- Machiavelli, Austen, Melville, Kafka | 26 (all human) |

The second exists because a high score there cannot be anything but an error: the
writing predates language models by a century or more. Optimising on the first
corpus alone produces a threshold that mislabels literature.

| | Result |
|---|---|
| Overall AUC | 0.974 |
| AI reaching "Suspicious" or above | 90% |
| Human text wrongly called "Likely AI" | 1 of 66 |
| Literary passages flagged | **0 of 26** |

**What does not work.** Short text is unreliable below roughly 80 words and
settles from about 200. Hand-edited AI loses fingerprints with every rewriting
pass. Source code is outside what these engines do: in testing they never falsely
accused human code, and never caught machine-written code either -- so we do not
claim they can.

The failures are published too, including three engines found scoring backwards
and two loading a randomly initialised network while carrying real ensemble
weight. Read them at
[sloptotal.com/detect/ai-detector-benchmark/](https://sloptotal.com/detect/ai-detector-benchmark/)
and [sloptotal.com/detect/ai-detector-false-positives/](https://sloptotal.com/detect/ai-detector-false-positives/).

## Quick Start

### Requirements

- **Python 3.10+** (3.11 recommended — macOS ships 3.9, which is too old)
- **4 GB RAM** minimum (lite profile); **8 GB** standard; **16 GB+** for best CPU throughput
- **No GPU required** — all engines run on CPU; CUDA optional for faster inference
- ~2 GB disk for HuggingFace model cache on first run

### Install

```bash
# Clone and install
git clone https://github.com/pablocaeg/sloptotal.git
cd sloptotal

# Use Python 3.10+ explicitly (example: Homebrew on macOS)
python3.11 -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Optional: copy env template
cp .env.example .env

# Start (auto-detects hardware, downloads models on first run)
./start.sh
# or manually:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

> **Re-scanning the same URL?** Results are cached by content hash. After upgrading dependencies, stale failure reports are purged automatically on startup. Run a fresh scan if you previously saw "Model loading failed".

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

Every engine links to its page on sloptotal.com, which carries its measured scores against both corpora. AUC below is the probability the engine ranks a random AI passage above a random human one: 1.0 is perfect, 0.5 is a coin flip.

### Neural Classifiers

| Engine | Model | AUC | Notes |
|---|---|---|---|
| [Desklib DeBERTa](https://sloptotal.com/engines/desklib-deberta/) | DeBERTa-v3-large (435M) | 1.000 | Strongest separation in our own tests |
| [SuperAnnotate](https://sloptotal.com/engines/superannotate/) | RoBERTa-large (355M) | 0.989 | No measurable bias against archaic prose |
| [E5-Small](https://sloptotal.com/engines/e5-small/) | E5 + LoRA (33M) | 0.999 | Matches far larger models at 33M params |
| [TMR Detector](https://sloptotal.com/engines/tmr-detector/) | RoBERTa-base (125M) | 1.000 | RAID-trained, so RAID scores flatter it |
| [BERT-tiny RAID](https://sloptotal.com/engines/bert-tiny-raid/) | BERT-tiny (4.4M) | 1.000 | Answers in milliseconds |
| [ReMoDetect](https://sloptotal.com/engines/remodetect/) | DeBERTa (184M) | 0.941 | Targets RLHF-aligned LLMs |
| [ChatGPT Detector](https://sloptotal.com/engines/chatgpt-detector/) | RoBERTa-base (125M) | 0.829 | ChatGPT-specific |
| [Fakespot](https://sloptotal.com/engines/fakespot/) | RoBERTa-base (125M) | 0.999 | Accurate on modern text, but +0.533 bias on pre-1920 prose |
| [OpenAI Detector](https://sloptotal.com/engines/openai-detector/) | RoBERTa-base (125M) | 0.771 | The 2019 GPT-2 detector; weaker on modern LLMs |

### Statistical Methods

| Engine | Method | AUC |
|---|---|---|
| [Log-Rank](https://sloptotal.com/engines/log-rank/) | Average log-rank under GPT-2 | 0.909 |
| [GLTR](https://sloptotal.com/engines/gltr/) | Token rank distribution | 0.904 |
| [Perplexity](https://sloptotal.com/engines/perplexity/) | GPT-2 perplexity scoring | 0.901 |
| [Cross-Perplexity](https://sloptotal.com/engines/cross-perplexity/) | Two-model perplexity comparison | 0.891 |
| [Fast-DetectGPT](https://sloptotal.com/engines/fast-detectgpt/) | Conditional probability curvature | 0.890 |
| [Binoculars](https://sloptotal.com/engines/binoculars/) | Cross-entropy ratio between two LMs | 0.836 |
| [DivEye](https://sloptotal.com/engines/diveye/) | Surprisal diversity | 0.730 |

### Linguistic Heuristics

| Engine | Signal | AUC |
|---|---|---|
| [Structural Analysis](https://sloptotal.com/engines/structural-analysis/) | Em-dash usage, sentence uniformity | 0.836 |
| [Linguistic Markers](https://sloptotal.com/engines/linguistic-markers/) | AI-preferred phrases ("delve", "tapestry"...) | 0.713 |
| [Formulaic Patterns](https://sloptotal.com/engines/formulaic-patterns/) | Cliche openings and closings | 0.698 |
| [Vocabulary Richness](https://sloptotal.com/engines/vocabulary-richness/) | Type-token ratio, hapax legomena | 0.583 |
| [Readability Uniformity](https://sloptotal.com/engines/readability-uniformity/) | Cross-paragraph consistency | 0.581 |
| [Burstiness](https://sloptotal.com/engines/burstiness/) | Per-sentence perplexity variance | 0.582 |
| [Sentiment & Hedging](https://sloptotal.com/engines/sentiment-and-hedging/) | Hedging and forced balance | 0.522 |

The linguistic heuristics are weak on their own. They are kept because they fail *independently* of the neural classifiers, which is what makes them useful as tiebreakers rather than as evidence.

## Scoring

The final score is **calibrated**, not a simple average, and every weight is
derived from measurement rather than intuition. See
[tests/eval/FINDINGS.md](tests/eval/FINDINGS.md) and
[sloptotal.com/detect/ai-detector-ensemble/](https://sloptotal.com/detect/ai-detector-ensemble/).

1. **Anchored on the unbiased classifiers** -- Desklib, SuperAnnotate, E5 and
   ReMoDetect all score high AUC with no measurable bias against older prose.
   Their consensus is blended 60/40 with the full weighted set.
2. **Weights from measurement** -- each engine's share is proportional to
   Somers' D (2*AUC - 1), scaled down by any bias it shows against archaic
   writing. RAID-trained engines are damped because our corpus is RAID.
3. **Confidence from agreement** -- a tight cluster across independent engine
   families is trustworthy; one confident engine is not.
4. **Skepticism, but only when earned** -- unanimous high classifier scores are
   damped *only* when the text itself carries human markers (contractions,
   first-person, slang). Applied unconditionally it fired on 69 of 70 AI samples
   and 0 of 66 human ones, suppressing correct detections.

Fakespot was previously the anchor, weighted 0.13. It is accurate on modern text
(AUC 0.999) but scored pre-1920 human prose at 0.645 against 0.112 for modern
human writing -- the largest bias of any engine -- and anchoring amplified it.
Machiavelli scored 62.5. After demotion to 0.033, literary passages average 10.2
and none is flagged.

## Hardware Requirements

SlopTotal auto-detects CPU, RAM, and GPU on startup and picks a profile (`lite`, `standard`, or `performance`).

| Profile | RAM | CPU | GPU | Notes |
|---------|-----|-----|-----|-------|
| Lite | 4 GB | 2 cores | None | All engines, slower |
| Standard | 8 GB | 4 cores | None | Default for most laptops |
| Performance | 16 GB+ | 6+ cores | CUDA optional | Pool replicas, max throughput |

**High-RAM CPU servers (e.g. 64 GB, no GPU):** you automatically get the `performance` profile. With no CUDA, all inference stays on CPU but you can run more concurrent workers and model pool replicas:

```bash
# Tune for a 64 GB CPU-only server
export SLOPTOTAL_PROFILE=performance
export SLOPTOTAL_TORCH_THREADS=8
export SLOPTOTAL_FULL_WORKERS=8
export SLOPTOTAL_SNIPPET_WORKERS=6
export SLOPTOTAL_MAX_CONCURRENT_FULL=4
export SLOPTOTAL_POOL_FAKESPOT=2
export SLOPTOTAL_POOL_TMR=2
./start.sh
```

First full scan downloads ~2 GB of models and may take 1–2 minutes while weights load; subsequent scans are much faster.

Hardware is auto-detected on startup. Override with environment variables:

```bash
SLOPTOTAL_TORCH_THREADS=4
SLOPTOTAL_FULL_WORKERS=6
SLOPTOTAL_SNIPPET_WORKERS=4
SLOPTOTAL_MAX_CONCURRENT_FULL=3
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TypeError: unsupported operand type(s) for \|` on startup | Python 3.9 or older | Use Python 3.10+ (`python3.11 -m venv venv`) |
| `ModuleNotFoundError: No module named 'bs4'` | Missing dependency | `pip install -r requirements.txt` (includes `beautifulsoup4`) |
| `Model loading failed` / tokenizer enum errors | Outdated `tokenizers` (<0.19) | `pip install -U 'transformers>=4.46' 'tokenizers>=0.21'` and restart |
| Old scans still show engine failures | Cached report from before fix | Restart server (auto-purges stale cache) and run a **new** scan |
| Engines stuck on "PENDING" in UI | Viewing an old report URL | Go to `/` and submit a fresh analysis |

Verify all engines loaded:

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
# Expect: "status": "healthy", "engines": 23
```

## Roadmap

See [TODO.md](TODO.md) for planned engines — including **Qwen** and **Gemma** classifiers and perplexity models optimized for high-RAM CPU servers.

## Related Projects & Reading

**Similar tools**
- [distil-labs/distil-ai-slop-detector](https://github.com/distil-labs/distil-ai-slop-detector) — 270M Gemma model, runs in the browser
- [Flamehaven01/AI-SLOP-Detector](https://github.com/Flamehaven01/AI-SLOP-Detector) — static analyzer for AI-generated *code* (complementary to text detection)
- [GLTR](http://gltr.io/) — visual token-rank inspection (inspiration for our GLTR engine)

**Papers & benchmarks**
- [RAID benchmark](https://arxiv.org/abs/2405.07940) (ACL 2024) — adversarial AI text detection dataset; several SlopTotal engines are RAID-trained
- [Detecting the Machine (2026)](https://arxiv.org/pdf/2603.17522) — cross-architecture detector benchmark; ensemble methods outperform single detectors
- [EditLens / Greyscope](https://arxiv.org/abs/2510.03154) — human vs. AI-edited vs. AI-generated classification (candidate Qwen engine)

**Guides**
- [Detecting AI Slop: Techniques & Red Flags](https://www.glukhov.org/post/2025/12/ai-slop-detection/) — perplexity, classifiers, and ensemble approaches

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
