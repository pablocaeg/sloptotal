# Changelog

All notable changes to SlopTotal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `POST /api/report/{id}/feedback`: visitors can say who actually wrote a text
  (human, AI, mixed, not sure). The answer is stored with the overall score and
  each engine's score, never the text, so it outlives the 30-day report purge.
  `python -m scripts.feedback_report` summarises it: agreement with the
  verdict and each engine's AUC against visitor labels.

### Fixed
- `scan_log`, which keeps text excerpts and URLs from snippet and quick scans,
  was never purged. It now follows the same retention window as reports.

### Changed
- CI runs the unit tests on Python 3.10, 3.11, 3.12 and 3.13, the versions the
  README supports.
- The February 2026 research notes moved to `docs/research/`, marked as
  historical; `docs/VISION.md` no longer implies the engines detect code.
- Issue forms point questions and ideas to Discussions.

### Added
- `CITATION.cff`, so the repository can be cited.

## [1.1.0] - 2026-09-28

### Added
- **Site check**: detects websites built with AI app builders (Lovable, v0,
  Bolt, Base44, Replit, Same) from fingerprints verified on live deployments.
  New home-page tab, a card on URL reports, and `POST /api/scan/site`.
- **Document upload**: `.pdf`, `.docx`, `.txt` and `.md` on the Text tab and
  `POST /api/extract`.
- Unit test suite (seconds, no model downloads) and `scripts/smoke_test.py`,
  an end-to-end check of every route and all 23 engines.
- `tests/eval/candidate_models.py` to measure new Hugging Face detectors.
- `SLOPTOTAL_API` for `tests/eval/run_any.py`, to re-measure a local instance.
- `AGENTS.md`, a brief for contributors and AI coding assistants.
- Semver Docker image tags on releases; Dependabot.

### Fixed
- Requests arriving while models were still loading could get a model without
  its tokenizer and score 0.0 on four classifiers (a "Clean" verdict).
- Concurrent model loads could leave GPT-2's output head randomly initialised,
  pinning Binoculars at 1.0. All loads now share one lock.
- URL scans could be pointed at private, loopback or cloud-metadata addresses.
- The report page coloured scores with hardcoded bands that disagreed with the
  verdict text.
- CI was red on a lint error; its test job had never run a test.

### Changed
- Web dependencies upgraded (FastAPI 0.141, Starlette 1.7, pydantic 2.13,
  httpx 0.28, trafilatura 2.2). transformers is capped below 6; 5.x reproduces
  every engine score exactly.
- Scripts moved from the repo root and `tests/` to `benchmarks/`.
- The stale `frontend/` and `extension/` copies were removed (the site and the
  extension have their own repositories).

## [1.0.1] - 2026-07-03

### Added
- Cache invalidation for reports with engine load failures
- Startup purge of stale cached reports

### Changed
- `requirements.txt`: `transformers>=4.46`, `tokenizers>=0.21`, `beautifulsoup4`
- README: Python 3.11 setup, troubleshooting, high-RAM CPU tuning, related reading

### Fixed
- Neural engine load failures caused by outdated `tokenizers` (<0.19)
- Stale cached reports serving pre-fix "Model loading failed" results

## [1.0.0] - 2026-03-21

### Added
- 23 AI detection engines (9 neural, 7 statistical, 7 linguistic)
- FastAPI backend with SSE streaming
- Calibrated ensemble scoring
- Hardware-aware autoconfig (lite/standard/performance profiles)
- Queue management with backpressure
- Content hash caching
- Astro + Preact frontend deployed to Cloudflare Pages
- Chrome Extension (Manifest V3) for Google Search and LinkedIn
- Docker support with model volume persistence
- URL scanning with page type classification
- CI/CD pipeline with GitHub Actions (lint, test, build, deploy)
- Issue templates for bugs, features, and new engine proposals
- Pull request template with review checklist
- CONTRIBUTING.md with development setup and engine contribution guide
- CODE_OF_CONDUCT.md (Contributor Covenant)
- SECURITY.md with vulnerability reporting process
- `.env.example` documenting all environment variables
- `.dockerignore` for smaller Docker build context
- AI agent suite for contributors (11 specialized agents, works with any AI tool)
- Agent documentation with workflow pipelines and diagrams

### Changed
- Dockerfile improved with multi-stage build, non-root user, and health check
- README updated with real GitHub URL, badges, and contributor section
- `.gitignore` updated to track `.claude/agents/` and ignore lighthouse reports
