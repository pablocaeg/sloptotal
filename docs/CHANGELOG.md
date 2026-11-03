# Changelog

All notable changes to SlopTotal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.3.0] - 2026-11-03

### Added
- **GPU inference.** Every model now runs on CUDA when torch can see a GPU;
  before, seven of them stayed on the CPU, and a typo (`total_mem`) meant the
  GPU profile was never picked. On an RTX 5070 Ti, 12 texts take 5.3 s instead
  of 319 s, with identical scores (#169).
- **The score range while a report runs.** Cheap engines are queued first, the
  report streams where the score can still land, and says which model engines
  are running and when the score is final (#142, #143, #144, #147).
- **A daily quota for direct API use** on public instances:
  `SLOPTOTAL_DIRECT_DAILY_LIMIT` calls per IP per day from outside
  `SLOPTOTAL_FIRST_PARTY_ORIGINS`. Off by default (#162).
- `fast: true` on the web form request: half the windows per classifier, so the
  windowed classifiers take about a third less time for a median score change
  of one point (#164).
- Example clients in Node.js (#140) and Ruby (#178).
- READMEs in Chinese, Russian (#163) and Spanish (#177).
- The site check recognises Emergent (#151).
- Catalan is detected instead of being read as Spanish (#145); Thai, Lao, Khmer
  and Burmese words are counted by characters (#136); Finnish, Czech and
  Hungarian are recognised and marked unsupported (#126); the report page shows
  the detected language (#122).
- Word tables are extracted from `.docx` uploads (#130).
- The report page highlights the phrases Linguistic Markers found (#105),
  remembers your feedback answer after a reload (#118) and has the
  sloptotal.com design (#95, #97, #99, #103, #104).
- Docs: how the overall score is calibrated (`docs/CALIBRATION.md`, #149), RAM
  and latency per engine (`docs/MODELS.md`, #154), the quick-path calibration
  (#119), the performance benchmarks (#128), OpenAPI tags and request examples
  in `/docs` (#107, #132).
- A weekly link check for the README and docs (#150), a Docker build on pull
  requests that touch the image (#186), and CodeQL and OpenSSF Scorecard
  scanning (#187).

### Changed
- The quick and paragraph scores (`/api/quick-score`, `/api/paragraph-score`,
  used by the Chrome extension) are now calibrated on SlopBench like the full
  report: a logistic fit over the quick engines, with short texts pulled toward
  the middle and the band edges at measured human false-positive rates
  (`tests/eval/slopbench/fit_quick.py`). The old hand-weighted formula called
  12.5% of human texts AI, 35% of TOEFL essays and 11 of 87 classic books; the
  fit calls 1.4% of human texts AI and 1 of 87 classics (#100, #101).
- The startup banner prints the real engine count, and the unused
  `SLOPTOTAL_LITE` flag is gone (#165).
- The docs give the real footprint: about 9 GB of downloads and 8.3 GB of RAM
  (#166).
- Every benchmark script reads the server address from `SLOPTOTAL_URL` (#183).
- ruff also checks import order, pyupgrade rules and file encodings (#138,
  #139, #176). Quick-scan thresholds live in `app/config.py` (#96, #125).
- fastapi 0.162.0, pydantic 2.14.1, trafilatura 2.3.1, pypdf 6.21.4 (#180,
  #182).

### Fixed
- A failed write on a worker thread's database connection is rolled back;
  before, it left the connection in a broken transaction and reports could stay
  at "Scanning..." (#152).
- Public endpoints no longer return scanned texts or URLs, and a test keeps it
  that way (#148, #168).
- DOCX uploads keep paragraphs and tables in document order (#153).
- Text files are read and written as UTF-8, so the tests pass on Windows
  (#176, #184).
- The queue wait counts long jobs as long and stays sane after a restart
  (#146).
- Keyboard focus stays inside the queue dialog (#185), and upload status is
  announced to screen readers (#129).
- Copy link works on self-hosted servers without HTTPS (#134), and pages that
  need JavaScript get a clear error (#133).

### Tests
- Direct tests for the calibration helpers, the feedback report's AUC edge
  cases, the model update inventory, Burstiness's early returns and the
  detection of more languages (#106, #124, #131, #135, #137).

## [1.2.0] - 2026-10-10

### Added
- **SlopBench** (`tests/eval/slopbench/`): a public benchmark of 3,252 texts.
  It has 1,626 human texts written before ChatGPT and 1,626 AI texts on the
  same topics and at the same lengths, written by 14 current models across 15
  kinds of writing. There are also hard cases (paraphrased, humanized,
  AI-polished), a datasheet, and the scripts that build, score and analyse it.
  Results can be broken down by text length (#61).
- Reports say which language they scored (`language`) and how far detection
  is trusted in it (`language_support`: supported, experimental or
  unsupported).
- `POST /api/report/{id}/feedback`: visitors can say who actually wrote a text
  (human, AI, mixed, not sure). The answer is stored with the overall score and
  each engine's score, never the text, so it outlives the 30-day report purge.
  `python -m scripts.feedback_report` summarises it: agreement with the
  verdict and each engine's AUC against visitor labels.
- `/health` reports which engines loaded, not only how many are registered
  (#41).
- `examples/python_client.py`, a small client for the JSON API (#42).
- A pre-commit config that runs ruff (#43), and a healthcheck in
  `docker/docker-compose.yml` (#64).
- `CITATION.cff`, so the repository can be cited.

### Changed
- **The score is calibrated on SlopBench.** A logistic model fitted on
  SlopBench replaces the hand-set weights, with a separate fit and offset for
  other languages. On kinds of writing the model was not tuned on:
  - English: AUC went from 0.904 to 0.942. Human texts called "Likely AI"
    dropped from 7.7% to 1.7%, and human texts flagged at all from 14.1% to
    3.9%.
  - Other languages: AUC went from 0.731 to 0.910.
- The 30/45/55/80 bands now sit where a measured share of human writing
  begins: 45 is the top 5% of human text, 55 the top 2% and 80 the top 0.5%.
  Confidence comes from the score.
- Language support:
  - supported: Spanish, French, German, Italian, Portuguese, Dutch, Polish,
    Russian and Japanese;
  - experimental: Arabic and Korean;
  - not reliable yet, and the report says so: Hindi, Turkish and Chinese.
- Short texts in other languages are held back the way short English texts
  already were. Texts in scripts written without spaces (Chinese, Japanese,
  Thai, Lao, Khmer, Burmese) skip that adjustment, and Chinese and Japanese
  words are counted by character.
- Text of any length is accepted and kept whole in the report.
- **Faster long texts.** The three large models read at most four
  non-overlapping windows. In a production-shaped load test, the slowest 10%
  of analyses finished about 40% sooner (56 s down to 34 s), with the same AUC
  to within 0.001.
- **A fast lane for short texts.** Texts of up to 350 words get their own
  queue and threads, and the single-model classifiers are handed over window
  by window. At twice peak traffic, the worst wait for a short text fell from
  134 s to 26 s.
- Full analyses wait in a real queue, and one text can no longer hold the
  models indefinitely.
- The Docker image runs Python 3.14. CI tests 3.10 to 3.14.
- Ruff's Bugbear rules are on, and exception context is preserved (#58).
- Every `SLOPTOTAL_*` setting is documented in the README, and a test keeps
  it that way (#74).
- The February 2026 research notes moved to `docs/research/`, marked as
  historical. `docs/VISION.md` no longer implies the engines detect code.
- Issue forms point questions and ideas to Discussions.

### Fixed
- A cached report is reused only when the current calibration scored it.
- URL scans that cannot be fetched answer 502 instead of 500.
- Short Thai, Japanese and Chinese texts no longer score near 0 because their
  words were undercounted.
- `scan_log`, which keeps text excerpts and URLs from snippet and quick scans,
  was never purged. It now follows the same retention window as reports.

### Tests
- New tests for the page classifier (#45), autoconfig (#46), document
  extraction edge cases (#78) and endpoint capacity (#79).

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
