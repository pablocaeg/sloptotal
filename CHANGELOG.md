# Changelog

All notable changes to SlopTotal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `TODO.md` roadmap for Qwen and Gemma detection engines
- Cache invalidation for reports with engine load failures
- Startup purge of stale cached reports

### Changed
- `requirements.txt`: `transformers>=4.46`, `tokenizers>=0.21`, `beautifulsoup4`
- README: Python 3.11 setup, troubleshooting, high-RAM CPU tuning, related reading

### Fixed
- Neural engine load failures caused by outdated `tokenizers` (<0.19)
- Stale cached reports serving pre-fix "Model loading failed" results

## [1.0.0] - 2025

### Added
- 23 AI detection engines (9 neural, 7 statistical, 7 linguistic)
- FastAPI backend with SSE streaming
- Calibrated scoring with Fakespot-dominant weighting
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
