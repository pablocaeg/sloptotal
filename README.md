<p align="center">
  <a href="https://sloptotal.com"><img src="docs/assets/banner.jpg" alt="SlopTotal: open-source AI text detector that runs 23 detection engines on your own hardware" width="100%"></a>
</p>

<p align="center">
  <a href="https://github.com/pablocaeg/sloptotal/actions/workflows/ci.yml?query=branch%3Amaster"><img src="https://img.shields.io/github/actions/workflow/status/pablocaeg/sloptotal/ci.yml?branch=master&event=push&label=CI" alt="CI status"></a>
  <a href="https://github.com/pablocaeg/sloptotal/releases"><img src="https://img.shields.io/github/v/release/pablocaeg/sloptotal?color=b5282e" alt="Latest release"></a>
  <a href="https://github.com/pablocaeg/sloptotal/pkgs/container/sloptotal"><img src="https://img.shields.io/badge/docker-ghcr.io-1a1a18?logo=docker&logoColor=white" alt="Docker image"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3d3b37" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2d8a4e" alt="MIT license"></a>
  <a href="https://sloptotal.com"><img src="https://img.shields.io/badge/live%20demo-sloptotal.com-b5282e" alt="Live demo"></a>
</p>

# SlopTotal

**VirusTotal for AI-generated text.** Paste text, drop in a PDF or Word file, or
give it a URL. Twenty-three independent AI detectors (neural classifiers,
statistical tests and linguistic heuristics) score it in parallel, and a
calibrated ensemble turns their votes into one verdict you can inspect engine by
engine. It runs on your own CPU, so nothing you scan leaves your machine.

It is a free, self-hosted, open-source alternative to hosted AI content
detectors such as GPTZero, Originality.ai, Copyleaks, ZeroGPT and Humalingo.
Instead of one number from one model, it shows you every model's opinion, and
it publishes how accurate that is, failures included.

<p align="center">
  <img src="docs/assets/demo.gif" alt="Pasting AI-written text into SlopTotal and watching 23 detection engines report in real time" width="820">
</p>

**Try it:** [sloptotal.com](https://sloptotal.com) · **Run it:** `docker run -p 8000:8000 ghcr.io/pablocaeg/sloptotal`

## Features

- **23 detection engines, one calibrated score.** DeBERTa and RoBERTa
  classifiers, Binoculars, Fast-DetectGPT, GLTR, perplexity and burstiness
  tests, and stock-phrase heuristics. Results stream in as each engine finishes.
- **Text, URLs and documents.** Paste text, scan a web page (main content is
  extracted automatically), or upload `.pdf`, `.docx`, `.txt` or `.md`.
- **Site check: was this website vibe-coded?** Finds the fingerprints that
  Lovable, v0, Bolt, Base44, Replit and Same leave in the sites they deploy,
  and shows the evidence for each one. [How it works](#site-check-detect-sites-built-with-ai-app-builders)
- **Per-paragraph heat map** through the API, to see which parts read as AI.
- **Measured, not claimed.** Every accuracy number below comes with the corpus,
  the harness and the raw per-sample scores.
- **Private by default.** Self-hosted, no third-party AI APIs, no tracking,
  reports deleted after 30 days.
- **CPU-only is fine.** Auto-detects your hardware; 4 GB RAM is enough for the
  lite profile, a GPU is optional.
- **JSON API and a [Chrome extension](https://github.com/pablocaeg/sloptotal-extension)**
  that marks AI-looking results in Google Search and LinkedIn.

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

Re-measured in September 2026 on a fresh RAID sample (180 texts) with upgraded
dependencies: AUC 0.979, 1 of 40 human texts called "Likely AI", 0 of 26
literary passages flagged.

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

## Command line and MCP server

No install needed with [uv](https://docs.astral.sh/uv/):

```bash
uvx --from "git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal check essay.md
```

```
essay.md   72.4  Likely AI-generated  (412 words)
  top engines: Desklib DeBERTa 0.99, ReMoDetect 0.95, SuperAnnotate 0.93
  report: https://sloptotal.com/report/?id=3f9c1a7b2d4e
```

`sloptotal check docs/*.md --fail-above 55` exits 1 when a file reads as AI,
for CI or a pre-commit hook. `sloptotal mcp` is an MCP server, so Claude,
Cursor and other agents can check text and sites themselves:

```bash
claude mcp add sloptotal -- uvx --from "sloptotal[mcp] @ git+https://github.com/pablocaeg/sloptotal#subdirectory=client" sloptotal mcp
```

It uses the public API at `api.sloptotal.com`; set `SLOPTOTAL_URL` to use your
own server. More in [client/README.md](client/README.md).

## Quick start

### Docker (fastest)

```bash
docker run -p 8000:8000 -v sloptotal-models:/app/models ghcr.io/pablocaeg/sloptotal
```

Open <http://localhost:8000>. The first scan downloads about 2 GB of models into
the `sloptotal-models` volume, so later starts are quick. To build from source
instead, run `docker compose -f docker/docker-compose.yml up`.

### From source

Requires **Python 3.10+** (macOS ships 3.9, which is too old).

```bash
git clone https://github.com/pablocaeg/sloptotal.git
cd sloptotal
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./scripts/start.sh    # or: uvicorn app.main:app --port 8000
```

Check that every engine loads and scores, end to end:

```bash
python scripts/smoke_test.py          # against http://localhost:8000
```

## Site check: detect sites built with AI app builders

<p align="center">
  <img src="docs/assets/site-check.jpg" alt="SlopTotal Site check identifying a website built with Lovable from its asset paths and scripts" width="760">
</p>

"Is this website vibe-coded?" checkers mostly score style (Tailwind class
counts, missing security headers, buzzwords) and turn it into a percentage.
Hand-written sites share all of those traits. SlopTotal looks only for markers
the builders themselves leave in what they deploy, each one confirmed on live
sites or in the builders' own templates:

| Builder | Fingerprints |
|---|---|
| Lovable | `gptengineer.js` runtime, `/lovable-uploads/` assets, the Lovable badge, `/~flock.js`, `*.lovable.app` |
| v0 (Vercel) | `<meta name="generator" content="v0.app">` from v0's layout template, `*.vusercontent.net` |
| Bolt | `X-Powered-By: Bolt.new` header, `bolt.new/badge.js`, `*.bolt.host` |
| Base44 | `app.base44.com` platform calls, `base44_access_token`, `*.base44.app` |
| Replit | Replit Agent dev banner, Replit badge, `*.replit.app` |
| Same | assets served from `same-assets.com` |

A site with no marker may still have been written with AI: code exported from
these tools and hosted elsewhere, or written in an AI editor, carries no
fingerprint. So the result is evidence, not a probability. The page's copy is
scored separately by the text engines.

```bash
curl -X POST http://localhost:8000/api/scan/site \
  -H "Content-Type: application/json" -d '{"url": "example.com"}'
```

## API

| Endpoint | Method | What it does | Typical latency (CPU) |
|---|---|---|---|
| `/api/analyze` | POST | Full 23-engine report for `text` or `url` | 2-8 s |
| `/api/quick-score` | POST | 4 classifiers plus heuristics | 0.1-0.5 s |
| `/api/paragraph-score` | POST | Score per paragraph (heat map) | 1-3 s |
| `/api/scan/site` | POST | AI app builder fingerprints plus a copy score | 1-3 s |
| `/api/extract` | POST | Text from an uploaded `.pdf` / `.docx` / `.txt` (multipart `file`) | < 1 s |
| `/api/scan/snippets` | POST | Batch of 1-30 short snippets | ~0.5 s |
| `/api/scan/urls` | POST | Batch of 1-10 URLs, page-type aware | 1-5 s |
| `/api/engines` | GET | Engine metadata | instant |
| `/api/report/{id}` | GET | A stored report | instant |
| `/api/report/{id}/feedback` | POST | Record who actually wrote the text: `{"label": "human" \| "ai" \| "mixed" \| "unsure"}` | instant |
| `/api/queue/status` | GET | Queue capacity | instant |

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Your text to analyze here..."}'
```

From Python, [`examples/python_client.py`](examples/python_client.py) analyses a
text, prints the five engines scoring highest and runs a site check, waiting
in the queue when the server is busy:

```bash
python examples/python_client.py "Paste at least 50 characters of text here..." example.com
```

The response lists every engine with its score, verdict and a plain-language
detail line, plus `overall_score` (0-100) and `overall_verdict`.

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

## Configuration

SlopTotal detects CPU, RAM and GPU at startup and picks a profile. Everything
can be overridden with environment variables; see [`.env.example`](.env.example).

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
./scripts/start.sh
```

| Variable | Default | Purpose |
|---|---|---|
| `SLOPTOTAL_PROFILE` | auto | `lite`, `standard` or `performance` |
| `SLOPTOTAL_RETENTION_DAYS` | `30` | Delete reports after N days (`0` keeps them) |
| `SLOPTOTAL_ALLOW_PRIVATE_URLS` | off | Let URL scans reach private or intranet hosts (blocked by default) |
| `HF_HOME` | `./models` | Where model weights are cached |

## FAQ

**Can AI detectors be trusted?** Not blindly. No detector, this one included,
should be the only evidence for an accusation. That is why SlopTotal shows
all 23 votes, how much they agree, and its measured false-positive rate. Short
text (under about 80 words) and heavily edited AI text are unreliable for every
detector.

**Does it detect ChatGPT, Claude, Gemini, Llama and Mistral?** The evaluation
corpus includes GPT-4, ChatGPT, Llama and Mistral output. The classifiers were
trained on a wider mix. Newer models are covered as far as they share those
fingerprints; the [evaluation harness](tests/eval/) lets you measure any model
you care about.

**Will it flag classic literature or formal writing?** Not in our tests: none
of the 26 passages from Austen, Melville, Kafka, Machiavelli and others is
flagged. Pre-1920 prose is part of the evaluation precisely because naive
detectors fail on it.

**Is my text stored or shared?** It is processed on the server you run. Reports
are kept for 30 days (configurable) so report links work, and nothing is sent
to an outside service.

**Can it detect AI-generated code?** No, and we do not claim it can: in testing
the engines never flagged human code but never caught machine-written code
either. The Site check reports which AI app builder produced a website, which is
a different question.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `TypeError: unsupported operand type(s) for \|` at startup | Python 3.9 or older; use 3.10+ |
| An engine reports `Model loading failed` | Check disk space and network for the first model download, then restart; `python scripts/smoke_test.py` shows which engine fails |
| First scan is slow | Models are loading; later scans take seconds |
| A URL scan says "private network address" | Intended; set `SLOPTOTAL_ALLOW_PRIVATE_URLS=1` to scan intranet pages |

## Project layout

```
app/            FastAPI backend: engines, ensemble, site fingerprints, API
web/            The web UI (Jinja2 templates, vanilla JS, no build step)
tests/          Unit tests (seconds, no downloads) and tests/eval/ accuracy harness
scripts/        smoke_test.py (end-to-end) and the model drift check
benchmarks/     Speed and load scripts
```

[ARCHITECTURE.md](docs/ARCHITECTURE.md) covers the internals. [AGENTS.md](AGENTS.md)
is a short brief for contributors and AI coding assistants.

## Newer open detectors we measured

Detector models keep appearing on Hugging Face, each with its own accuracy
claim. Before adding any, we score them on the same two corpora. September 2026,
standalone, 180 RAID texts plus the 26 literary passages:

| Model | RAID AUC | Literary bias (lower is better) | Status |
|---|---|---|---|
| [Gradient](https://huggingface.co/ShantanuT01/gradient-ai-text-detector) (DeBERTa-v3-large) | 0.998 | 0.033 | Next engine to add |
| [Vanguard](https://huggingface.co/ShantanuT01/vanguard-ai-text-detector) (ModernBERT-large) | 0.998 | 0.037 | Candidate; poorly calibrated at 0.5 |
| [Earlybird-fast](https://huggingface.co/noumenon-labs/Earlybird-fast) (82M) | 0.913 | 0.040 | Candidate for fast snippet scans |
| [rasbt ModernBERT](https://huggingface.co/rasbt/ai-text-detector-modernbert) | 0.864 | 0.000 | Not added |

RAID-trained models score near 1.0 on RAID by construction and need a different
test set first. The full table, the models we excluded and why, and the raw
scores are in [tests/eval/FINDINGS.md](tests/eval/FINDINGS.md#newer-open-detectors-measured-standalone).
The roadmap is in [TODO.md](docs/TODO.md).

## Related projects and reading

- [RAID benchmark](https://arxiv.org/abs/2405.07940) (ACL 2024): adversarial AI text detection dataset used in our evaluation
- [Detecting the Machine (2026)](https://arxiv.org/pdf/2603.17522): cross-architecture detector benchmark; ensembles beat single detectors
- [EditLens](https://arxiv.org/abs/2510.03154): human vs AI-edited vs AI-generated classification
- [GLTR](http://gltr.io/): visual token-rank inspection, the inspiration for our GLTR engine
- [distil-labs/distil-ai-slop-detector](https://github.com/distil-labs/distil-ai-slop-detector): a 270M Gemma detector that runs in the browser
- [sloptotal-extension](https://github.com/pablocaeg/sloptotal-extension): the Chrome extension

## Contributing

Contributions are welcome, especially new engines with measurements. Start with
[CONTRIBUTING.md](.github/CONTRIBUTING.md).

- [Report a bug](https://github.com/pablocaeg/sloptotal/issues/new?template=bug_report.yml)
- [Request a feature](https://github.com/pablocaeg/sloptotal/issues/new?template=feature_request.yml)
- [Propose a new engine](https://github.com/pablocaeg/sloptotal/issues/new?template=new_engine.yml)
- [Ask a question or share results](https://github.com/pablocaeg/sloptotal/discussions)

If SlopTotal is useful to you, a star helps other people find it.

## License

MIT. Model weights keep their own licenses; see
[THIRD_PARTY_LICENSES.md](docs/THIRD_PARTY_LICENSES.md).
