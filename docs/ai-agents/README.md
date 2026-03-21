# AI Agent Suite for SlopTotal

SlopTotal ships with **11 specialized AI agents** that can autonomously navigate, build, test, review, and ship contributions to this project. The agents are structured system prompts grounded in the actual codebase — they work with **any AI coding assistant**, not just Claude Code.

## How It Works

Each agent is a Markdown file in `.claude/agents/` containing:

- **YAML frontmatter** — name, description, required tools, and model preference
- **Project knowledge** — architecture maps, file locations, and code patterns extracted from the real codebase
- **Step-by-step workflows** — what to read, what to build, what to verify
- **Guardrails** — explicit "What NOT to Do" rules to prevent common mistakes

The agents encode **institutional knowledge** about SlopTotal's architecture so that any AI assistant — whether Claude Code, Cursor, GitHub Copilot, ChatGPT, Gemini, Windsurf, or a custom tool — can contribute correctly without first spending hours understanding the codebase.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         .claude/agents/                              │
│                                                                      │
│  Each file is a self-contained system prompt with:                   │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │  Frontmatter │  │  Architecture │  │  Workflows & Guardrails   │  │
│  │  name, tools │  │  maps, paths  │  │  steps, quality gates,    │  │
│  │  model       │  │  patterns     │  │  "What NOT to Do"         │  │
│  └─────────────┘  └──────────────┘  └────────────────────────────┘  │
│                                                                      │
│  Any AI model that can read/write files and run shell commands       │
│  can use these prompts as context to contribute correctly.           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Using the Agents

### With Claude Code (native support)

Claude Code auto-discovers agents in `.claude/agents/`. Just reference them by name:

```bash
claude                     # open Claude Code in the repo
> @sloptotal-expert "How does the scoring calibration work?"
> @sloptotal-contribute "Add a new detection engine based on surprisal diversity"
```

### With Cursor / Windsurf / Continue

1. Open the agent file (e.g., `.claude/agents/sloptotal-feature-builder.md`)
2. Copy everything below the frontmatter (`---`) as a system prompt or instruction
3. Paste into your AI assistant's custom instructions / rules file
4. The agent prompt gives the AI all the context it needs

**Cursor example** — add to `.cursor/rules`:
```
# Paste the content of .claude/agents/sloptotal-feature-builder.md here
```

### With ChatGPT / Gemini / Any Chat Model

1. Open the agent file you need
2. Start a new conversation
3. Paste the agent's content as your first message, prefixed with:
   "Use the following as your system instructions for this conversation:"
4. Then ask your question or describe your task

### With GitHub Copilot Chat

Reference the agent file directly:
```
@workspace /explain Use .claude/agents/sloptotal-expert.md as context. How does SSE streaming work?
```

### Programmatic Usage (API / Scripts)

Any AI API can use these agents. Pass the file content as the system prompt:

```python
from pathlib import Path
from anthropic import Anthropic  # or openai, google.generativeai, etc.

agent_prompt = Path(".claude/agents/sloptotal-expert.md").read_text()
# Strip YAML frontmatter
agent_prompt = agent_prompt.split("---", 2)[2].strip()

client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    system=agent_prompt,
    messages=[{"role": "user", "content": "How does the scoring calibration work?"}],
)
```

---

## The 11 Agents

### Agent Map

```
                              ┌─────────────────────────────────┐
                              │      sloptotal-contribute       │
                              │       (Orchestrator)            │
                              │                                 │
                              │  Chains agents into end-to-end  │
                              │  pipelines with human           │
                              │  checkpoints at every stage     │
                              └───────────┬─────────────────────┘
                                          │
                      ┌───────────────────┼───────────────────┐
                      │                   │                   │
                      ▼                   ▼                   ▼
              ┌───────────────┐  ┌────────────────┐  ┌────────────────┐
              │   UNDERSTAND  │  │     BUILD      │  │    QUALITY     │
              └───────┬───────┘  └───────┬────────┘  └───────┬────────┘
                      │                  │                    │
          ┌───────────┴──────┐     ┌─────┴──────────────┐    ├──────────────┐
          │                  │     │     │     │    │    │    │              │
          ▼                  ▼     ▼     ▼     ▼    ▼    ▼    ▼              ▼
     ┌─────────┐    ┌──────────┐ ┌───┐ ┌───┐ ┌──┐ ┌──┐ ┌──┐ ┌──────┐ ┌─────────┐
     │ expert  │    │ complet- │ │fea│ │dep│ │op│ │os│ │ex│ │test  │ │reviewer │
     │         │    │ ionist   │ │tu-│ │lo-│ │ti│ │s │ │t-│ │writer│ │         │
     │ Navigate│    │          │ │re │ │yer│ │mi│ │  │ │en│ │      │ │ Code    │
     │ & ask   │    │ Find     │ │bui│ │   │ │ze│ │  │ │si│ │pytest│ │ review  │
     │ about   │    │ gaps     │ │ld-│ │CI/│ │r │ │  │ │on│ │      │ │ with    │
     │ code    │    │          │ │er │ │CD │ │  │ │  │ │  │ │      │ │ BLOCKER/│
     └─────────┘    └──────────┘ └───┘ └───┘ └──┘ └──┘ └──┘ └──────┘ │WARNING/│
                                                                       │SUGGEST │
                                                            ┌──────┐  └─────────┘
                                                       ┌───►│pr-   │
                                                SHIP──►│    │creat-│
                                                       │    │or    │
                                                       └───►└──────┘
```

### Agent Reference

| Agent | Role | What it knows | When to use |
|-------|------|---------------|-------------|
| **sloptotal-expert** | Navigate & explain | Full architecture map, all file paths, engine patterns, SSE flow, scoring calibration | Before building anything — understand what exists |
| **sloptotal-completionist** | Find gaps | Prioritized list of 17 known incomplete items ranked by severity | When you want to know what needs work |
| **sloptotal-feature-builder** | Build features | Engine templates, API endpoint patterns, Astro/Preact component patterns, design tokens | Adding new engines, endpoints, pages, or components |
| **sloptotal-deployer** | Infrastructure | CI/CD workflow templates, Dockerfile optimization, deployment strategy, monitoring | Setting up or improving CI/CD and deployment |
| **sloptotal-optimizer** | Improve quality | Frontend perf, SEO audit, accessibility checklist, backend optimization opportunities, Docker hardening | Performance, SEO, a11y, or security improvements |
| **sloptotal-open-source** | Community setup | GitHub templates, README structure, topics, labels, discoverability | Preparing the repo for public contributions |
| **sloptotal-extension-extractor** | Repo separation | Full extension architecture, extraction plan, standalone repo structure | Extracting the Chrome extension to its own repo |
| **sloptotal-test-writer** | Write tests | pytest patterns, fixtures, conftest template, parametrize examples, engine test patterns | After building, before review |
| **sloptotal-reviewer** | Code review | 30-point checklist across security, performance, API contracts, style, frontend patterns | Before submitting a PR |
| **sloptotal-pr-creator** | Ship changes | Branch naming, conventional commits, staging rules, PR description format | Final step — creating the pull request |
| **sloptotal-contribute** | Orchestrate | All agent capabilities, 6 pipeline templates, checkpoint protocol, context-passing format | Complex workflows spanning multiple agents |

---

## The Orchestrator: `sloptotal-contribute`

The orchestrator is the most powerful agent. It doesn't build things itself — it **coordinates the specialist agents** into end-to-end pipelines, passing context between them and pausing for human confirmation at critical decision points.

### How Orchestration Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION FLOW                               │
│                                                                         │
│   User Request                                                          │
│       │                                                                 │
│       ▼                                                                 │
│   ┌──────────────┐     ┌──────────────────────────────────────────┐    │
│   │ 1. CLASSIFY  │────►│ Match request to one of 6 pipelines:    │    │
│   │    request   │     │  A: Complete feature  D: Open-source     │    │
│   └──────────────┘     │  B: Optimize          E: Extract ext.   │    │
│                        │  C: Deploy/CI         F: New engine      │    │
│                        └────────────────────────┬─────────────────┘    │
│                                                 │                      │
│                                                 ▼                      │
│   ┌──────────────┐     ┌──────────────────────────────────────────┐    │
│   │ 2. RESEARCH  │────►│ Spawn analysis agents to understand     │    │
│   │              │     │ the current state before changing it     │    │
│   └──────────────┘     └────────────────────────┬─────────────────┘    │
│                                                 │                      │
│                                                 ▼                      │
│                        ┌──────────────────────────────────────────┐    │
│                  ┌─────┤      CHECKPOINT: Human confirms plan     │    │
│                  │     │      before any code is written          │    │
│                  │     └────────────────────────┬─────────────────┘    │
│                  │                              │ User approves        │
│     User says    │                              ▼                      │
│     "stop" or    │     ┌──────────────────────────────────────────┐    │
│     "change X"   │     │ 3. BUILD                                │    │
│                  │     │    Spawn builder agents with context     │    │
│                  │     │    from research step                    │    │
│                  │     └────────────────────────┬─────────────────┘    │
│                  │                              │                      │
│                  │                              ▼                      │
│                  │     ┌──────────────────────────────────────────┐    │
│                  │     │ 4. VERIFY                                │    │
│                  │     │    Import checks, build checks, tests    │    │
│                  │     │    Fix any failures                      │    │
│                  │     └────────────────────────┬─────────────────┘    │
│                  │                              │                      │
│                  │                              ▼                      │
│                  │     ┌──────────────────────────────────────────┐    │
│                  │     │ 5. REVIEW                                │    │
│                  │     │    Spawn reviewer agent                  │    │
│                  │     │    Fix BLOCKERs, address WARNINGs        │    │
│                  │     └────────────────────────┬─────────────────┘    │
│                  │                              │                      │
│                  │                              ▼                      │
│                  │     ┌──────────────────────────────────────────┐    │
│                  ├─────┤      CHECKPOINT: Human reviews changes   │    │
│                  │     │      before shipping                     │    │
│                  │     └────────────────────────┬─────────────────┘    │
│                  │                              │ User approves        │
│                  │                              ▼                      │
│                  │     ┌──────────────────────────────────────────┐    │
│                  │     │ 6. SHIP                                  │    │
│                  │     │    Spawn PR creator: branch, commit,     │    │
│                  │     │    push, open PR                         │    │
│                  │     └──────────────────────────────────────────┘    │
│                  │                                                     │
│                  └──► Orchestrator adjusts plan based on feedback      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Context Passing Between Agents

The orchestrator passes findings from one agent to the next using a structured format. This is what makes the pipeline coherent — each agent builds on what the previous one discovered:

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│   Expert     │         │  Feature Builder  │         │  Test Writer  │
│              │         │                   │         │              │
│ "The scoring │────────►│ "Expert found:    │────────►│ "Builder     │
│  system uses │ context │  - scoring is in  │ context │  created:    │
│  calibrated  │ handoff │    analyzer.py    │ handoff │  - new_eng.py│
│  weights in  │         │  - weights in     │         │  - registered│
│  config.py"  │         │    config.py      │         │    in        │
│              │         │  Your task: build  │         │    analyzer  │
│              │         │  a new engine"    │         │  Your task:  │
│              │         │                   │         │  write tests"│
└──────────────┘         └──────────────────┘         └──────────────┘
```

The format:
```
Previous agent found:
- [Key finding 1]
- [Key finding 2]
- [File paths affected]

Your task:
[Specific instruction for this agent]

Constraints:
- [Any constraints from earlier steps]
```

---

## The 6 Pipelines

### Pipeline A: Complete a Missing Feature

**Trigger**: "fix X", "complete Y", "finish Z"

```
Expert ──► Completionist ──► [ CHECKPOINT ] ──► Feature Builder ──► Test Writer ──► Reviewer ──► [ CHECKPOINT ] ──► PR Creator
  │              │                  │                   │                │              │                │              │
  │              │                  │                   │                │              │                │              │
  ▼              ▼                  ▼                   ▼                ▼              ▼                ▼              ▼
Understand    Identify          User picks          Build the       Write tests    Review for      User confirms  Branch,
the area      specific gaps     which gaps          implementation  for new code   correctness     changes        commit,
              and rank them     to address                                         and security    look good      push, PR
```

### Pipeline B: Optimize

**Trigger**: "optimize", "speed up", "improve performance"

```
Expert ──► Optimizer ──► [ CHECKPOINT ] ──► Implement ──► Measure ──► Reviewer ──► [ CHECKPOINT ] ──► PR Creator
  │            │                │                │            │            │                │              │
  ▼            ▼                ▼                ▼            ▼            ▼                ▼              ▼
Baseline    Identify        User picks       Apply        Compare      Review for      User confirms  Ship with
metrics     opportunities   optimizations    changes      before/after side effects    results OK     metrics
```

### Pipeline C: Set Up Deployment

**Trigger**: "set up CI", "deploy", "add GitHub Actions"

```
Expert ──► Deployer ──► [ CHECKPOINT ] ──► Implement ──► Reviewer ──► [ CHECKPOINT ] ──► PR Creator
  │            │                │                │            │                │              │
  ▼            ▼                ▼                ▼            ▼                ▼              ▼
Current     Design CI/CD    User confirms    Create        Review infra    User confirms  Ship
deployment  and infra plan  the plan         workflow      changes         ready to push
state                                        files
```

### Pipeline D: Open-Source Preparation

**Trigger**: "prepare for open source", "add issue templates"

```
Expert ──► Open Source ──► [ CHECKPOINT ] ──► Implement ──► Reviewer ──► [ CHECKPOINT ] ──► PR Creator
  │              │                 │                │            │                │              │
  ▼              ▼                 ▼                ▼            ▼                ▼              ▼
Audit docs    Plan all          User confirms    Create/update  Review docs    User confirms  Ship
and repo      needed changes    scope            README,        and templates  ready
setup                                            templates, etc.
```

### Pipeline E: Extract Extension

**Trigger**: "extract extension", "separate extension repo"

```
Expert ──► Ext. Extractor ──► [ CHECKPOINT ] ──► Implement ──► Reviewer ──► [ CHECKPOINT ] ──► Init Repo ──► PR Creator
  │              │                    │                │            │                │              │              │
  ▼              ▼                    ▼                ▼            ▼                ▼              ▼              ▼
Understand   Plan extraction,     User confirms    Create new    Review code    User confirms  Init git,      PR for
extension    identify files        plan and         repo          and docs       ready          first commit   monorepo
arch.        and changes          new repo name    structure                                                   update
```

### Pipeline F: Build a New Engine

**Trigger**: "add a new engine", "build X detector"

```
Expert ──► Research ──► [ CHECKPOINT ] ──► Feature Builder ──► Test Writer ──► Reviewer ──► [ CHECKPOINT ] ──► PR Creator
  │            │                │                   │                │              │                │              │
  ▼            ▼                ▼                   ▼                ▼              ▼                ▼              ▼
Understand  Research the     User confirms      Create engine,   Write engine   Full review,    User confirms  Ship
engine      detection        the approach       register, add    tests          verify weights  ready
patterns    method           is sound           weights, update                 sum to 1.0
                                                frontend
```

---

## Quality Gates

The orchestrator enforces quality gates between pipeline stages. A stage must pass its gate before the next stage begins:

```
┌─────────────────────────────────────────────────────────┐
│                    QUALITY GATES                         │
│                                                          │
│  After BUILDING:                                         │
│  ├─ Python import check passes                          │
│  ├─ No syntax errors                                    │
│  └─ Frontend build succeeds (if changed)                │
│                                                          │
│  After TESTING:                                          │
│  ├─ All unit tests pass                                 │
│  ├─ Or failures are explained and accepted              │
│  └─ ENGINE_WEIGHTS still sum to 1.0 (if engines added)  │
│                                                          │
│  After REVIEWING:                                        │
│  ├─ Zero BLOCKER issues remain                          │
│  ├─ All WARNINGs addressed or justified                 │
│  └─ SUGGESTIONs noted for follow-up                     │
│                                                          │
│  Before SHIPPING:                                        │
│  ├─ All checks pass                                     │
│  ├─ Changes are focused (one concern per PR)            │
│  └─ Human has explicitly approved                       │
└─────────────────────────────────────────────────────────┘
```

---

## Agent Details

### `sloptotal-expert` — Codebase Navigator

**Purpose**: Understand the codebase before changing it.

Contains a complete architecture map covering:
- All backend files, routes, and their purposes
- Both frontend systems (legacy Jinja2 `web/` and modern Astro `frontend/`)
- Chrome extension architecture (service worker, content scripts, popup)
- Critical patterns: SSE streaming flow, scoring calibration, engine registration
- Deployment stack: FastAPI + Cloudflare Pages + Docker

**Key rule**: Always reads actual code — never answers from assumption.

### `sloptotal-completionist` — Gap Finder

**Purpose**: Find what's broken, missing, or incomplete.

Contains a prioritized list of 17 known gaps ranked as HIGH / MEDIUM / LOW priority. Examples:
- HIGH: Missing automated tests, no environment variable docs
- MEDIUM: Phase A GPT-2 signals not wired, no error boundaries
- LOW: Missing favicon.ico, Google Fonts not self-hosted

**Key rule**: Reads the relevant files to confirm a gap still exists before reporting it.

### `sloptotal-feature-builder` — Feature Constructor

**Purpose**: Build new engines, API endpoints, pages, and components.

Contains complete templates for every type of feature:
- **New engine**: 7-step process from `BaseEngine` subclass through registration, weights, frontend metadata, and verification
- **New API endpoint**: Queue-aware pattern with proper error handling
- **New Astro page**: Layout, component, and styles following the design system
- **New Preact component**: Hooks, TypeScript interfaces, API integration

Also includes the full design token reference (CSS custom properties).

### `sloptotal-deployer` — Infrastructure Engineer

**Purpose**: Set up CI/CD, improve Docker, manage deployments.

Contains ready-to-use workflow files for:
- CI pipeline (lint, test, build, Docker)
- Frontend deployment (Cloudflare Pages via Wrangler)
- Backend deployment (GHCR + SSH deploy to VPS)
- Environment variable documentation
- Docker optimization (multi-stage build, non-root user, health check)
- Rollback strategy for both frontend and backend

### `sloptotal-optimizer` — Quality Improver

**Purpose**: Improve performance, SEO, accessibility, and security.

Contains an audit across 7 dimensions:
1. Frontend performance (fonts, hydration, bundle size)
2. SEO (meta tags, structured data, sitemap)
3. Accessibility (ARIA, focus management, keyboard nav)
4. Backend performance (already well-optimized; suggests compression, metrics)
5. Docker/container optimization
6. Security hardening (HSTS, CSP, rate limiting)
7. Code quality (linting, formatting, pre-commit hooks)

### `sloptotal-test-writer` — Test Engineer

**Purpose**: Create pytest unit and integration tests.

Contains:
- `conftest.py` template with shared fixtures (sample texts, temp DB, mock engine)
- Unit test patterns for schemas, score thresholds
- Engine interface compliance tests (all 23 engines implement BaseEngine correctly)
- Weight validation tests (sum to 1.0)
- API integration tests with FastAPI TestClient

**Key rule**: Tests behavior, not exact values. Never tests ML model accuracy.

### `sloptotal-reviewer` — Code Reviewer

**Purpose**: Review changes before they ship.

Contains a 30-point checklist organized as:
- **BLOCKERS** (must fix): Engine registration completeness, security, data integrity, API contracts
- **WARNINGS** (should fix): Performance, error handling, code style, frontend patterns
- **SUGGESTIONS** (nice to have): Documentation, testing, edge cases

Also lists false-positive patterns — things that look wrong but are intentionally that way.

### `sloptotal-pr-creator` — Shipping Agent

**Purpose**: Create clean branches, commits, and pull requests.

Contains:
- Branch naming conventions (`feat/`, `fix/`, `docs/`, etc.)
- Conventional commit message format
- Staging rules (always specific files, never `git add -A`)
- PR description template with Summary, Changes, Testing, and Notes
- List of files that should never be committed

### `sloptotal-open-source` — Community Prep

**Purpose**: Set up GitHub for public contributions.

Contains templates for all community health files:
- Issue templates (bug, feature, new engine) in YAML form format
- PR template with SlopTotal-specific checklist
- Recommended GitHub topics for discoverability
- README structure for compelling open-source presentation

### `sloptotal-extension-extractor` — Repo Separator

**Purpose**: Extract the Chrome extension into a standalone repository.

Contains:
- Complete extension file inventory and architecture
- New repo directory structure
- CI/CD for extension (lint, package, Chrome Web Store publish)
- Manifest V3 production considerations
- Plan for updating the monorepo after extraction

### `sloptotal-contribute` — Master Orchestrator

**Purpose**: Chain all other agents into end-to-end workflows.

Contains:
- Routing logic matching user requests to the right pipeline
- Context-passing format between agents
- Checkpoint protocol (what to show, when to pause)
- Error recovery strategy (re-run with more context, or fall back to direct work)
- Strict rules: never skip checkpoints, never auto-commit, never parallelize dependent agents

---

## Adapting for Other AI Tools

### System Prompt Extraction

Every agent file follows this structure:

```markdown
---
name: agent-name
description: When to use this agent
tools: Read, Write, Edit, Glob, Grep, Bash
model: opus
---

[System prompt content — this is the part you copy]
```

To use with any AI tool, extract everything below the second `---`. The frontmatter is Claude Code metadata; the body is a universal system prompt.

### Tool Mapping

The agents reference tool names from Claude Code. Here's how they map to other tools:

| Agent Tool | What It Does | Cursor / Copilot | ChatGPT | Manual |
|------------|-------------|-------------------|---------|--------|
| `Read` | Read file contents | Built-in file read | Upload file | `cat file` |
| `Write` | Create new file | Built-in file write | Copy output | `> file` |
| `Edit` | Modify existing file | Built-in edit | Copy output | Editor |
| `Glob` | Find files by pattern | Built-in search | N/A | `find . -name` |
| `Grep` | Search file contents | Built-in search | N/A | `grep -r` |
| `Bash` | Run shell commands | Terminal | N/A | Terminal |
| `WebSearch` | Search the web | N/A (use browser) | Built-in | Browser |
| `Agent` | Spawn sub-agent | N/A | New chat | New session |

### Creating Your Own Agents

To add a new agent to SlopTotal:

1. Create a `.md` file in `.claude/agents/` with the frontmatter format shown above
2. Ground it in the real codebase — read actual files, don't assume patterns
3. Include a "What NOT to Do" section with project-specific guardrails
4. Test it on a real task before committing
5. Add it to this documentation

---

## File Locations

```
.claude/agents/
  sloptotal-expert.md              # Codebase navigation & architecture
  sloptotal-completionist.md       # Gap analysis & missing features
  sloptotal-feature-builder.md     # Build engines, endpoints, pages
  sloptotal-test-writer.md         # pytest tests & fixtures
  sloptotal-reviewer.md            # Code review with BLOCKER/WARNING/SUGGESTION
  sloptotal-optimizer.md           # Performance, SEO, a11y, security
  sloptotal-deployer.md            # CI/CD, Docker, deployment
  sloptotal-open-source.md         # GitHub templates & discoverability
  sloptotal-extension-extractor.md # Extract extension to own repo
  sloptotal-pr-creator.md          # Git workflow & PR creation
  sloptotal-contribute.md          # Master orchestrator (chains all above)
```
