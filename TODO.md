# TODO

## Detection engines

- [ ] **Add Qwen and Gemma detection engines** — integrate the best available models from each family for CPU-only servers with ample RAM (64GB+). Candidates to benchmark:

  | Model | Params | RAM (est.) | Role | Notes |
  |-------|--------|------------|------|-------|
  | [distil-labs/distil-ai-slop-detector-gemma](https://huggingface.co/distil-labs/distil-ai-slop-detector-gemma) | 270M | ~0.5 GB | Fast classifier | Distilled from GPT-OSS-120B; strong on short–medium text |
  | [noumenon-labs/Earlybird-fast](https://huggingface.co/noumenon-labs/Earlybird-fast) | 82M | ~0.3 GB | Fast classifier | <50 ms on CPU; best on 100+ word passages |
  | [yaoandy107/greyscope-qwen3.5-4b](https://huggingface.co/yaoandy107/greyscope-qwen3.5-4b) | 4B | ~9 GB | High-accuracy | Human / AI-edited / AI-generated; EditLens-trained |
  | Qwen2.5-1.5B or 3B (base) | 1.5–3B | 3–6 GB | Perplexity / Binoculars | Pair with Gemma for cross-perplexity signals |
  | [google/gemma-3-1b-it](https://huggingface.co/google/gemma-3-1b-it) | 1B | ~2 GB | Perplexity / cross-LM | Lightweight observer model |

  **Plan:** add Gemma slop classifier + Qwen perplexity/cross-perplexity engines first (low integration cost), then evaluate Greyscope-class Qwen fine-tunes for a premium accuracy tier on `performance` profile.

## Infrastructure

- [ ] Pin `transformers`/`tokenizers` minimum versions in CI to prevent tokenizer format regressions
- [ ] Add `docs/MODELS.md` with per-engine HuggingFace links, RAM footprint, and CPU latency benchmarks

## Master architectural blueprint

- [ ] **Produce a structured architecture document (PDF or docs)** — SlopTotal: Master Architectural Blueprint

  **Vision:** Build the undisputed best free multi-engine AI detection platform in the world, mirroring the core aggregation philosophy of VirusTotal across natural text, programming code, multiple languages, and vertical subjects.

  ### 1. Hardware utilization & core detection mechanics

  With a 64 GB local system configuration, the backend has enough memory to load and run multiple deep token-analysis layers without relying on external commercial black-box APIs.

  - **Dual-model contrastive perplexity:** Standard prompt-based verification triggers heavy hallucinations. True precision relies on computing a mathematical surprise score (perplexity ratio). If a raw base model (e.g. Gemma 3 12B or Qwen 2.5 7B) reads a sequence and shows a low perplexity score, that statistically validates machine-generated output.
  - **Hardware distribution:** Apple Silicon unified memory runs large models efficiently across shared RAM. Dedicated PC setups route foundational models through VRAM (e.g. RTX 3090/4090) while deploying secondary classification models in system RAM.

  ### 2. Specialized open-weight model core grid

  Following the VirusTotal methodology, SlopTotal should establish specialized detection matrix pipelines optimized for localized linguistic variations and data structures.

  | Category | Target engine model | Core analytical specialization |
  |----------|---------------------|--------------------------------|
  | Google ecosystem | distil-labs/distil-ai-slop-detector-gemma | Optimized via structural distillation to trap generic, unedited Western LLM outputs and structural padding |
  | Multilingual / technical | tusarway/qwen3-0.6b-ai-detector | Extremely lightweight sequence classifier for complex Asian language scripts and localized translations |
  | High-speed pipeline | ModernBERT-base (custom fine-tuned) | 8k context window for primary fast-screening sweeps; drop clean text immediately |
  | Advanced code/math | Qwen/Qwen2.5-Coder-7B (perplexity) | Evaluates logical distribution patterns and next-token predictability across raw programming scripts |

  ### 3. Cross-domain scaling strategy

  **A. Coding exercise & source code detection**

  Standard textual analyzers cannot evaluate syntax accurately. Code-centric auditing needs alternative mechanics:

  - **Abstract syntax trees (AST):** Parse input with tree-sitter to profile programmatic structure. Human developers show chaotic architectural loops; AI assistants generate rigid, standardized blocks, repetitive variable chains, and uniform spacing.
  - **Coder-weight cross checks:** Test raw perplexity with models optimized for development syntax (DeepSeek-Coder, Qwen-Coder). High structural compliance signals code generation.

  **B. Multilingual ingestion engines**

  - **Western tier:** Route German, Spanish, and French toward Gemma 3 architectures for robust contextual understanding.
  - **Eastern tier:** Route Chinese, Korean, and Japanese through native Qwen clusters to avoid standard tokenizer failures.

  ### 4. Global aggregator SEO playbook

  Drive organic global traffic without paid marketing by scaling automated, high-intent architectural funnels:

  - **Programmatic target comparison hubs:** Automated landing pages focused on market alternatives (e.g. sloptotal.com vs competitors). Show multi-engine matrix transparency to capture user flow.
  - **International routing subfolders:** Avoid browser-only translation. Deploy native paths (e.g. `/es`, `/fr`) to optimize keyword indexes globally.
  - **Embeddable verification badges:** Lightweight open verification API with GitHub widgets and documentation banners (e.g. `[Sloptotal: Verified Human Code]`) to drive high-authority backlinks to the base domain.

