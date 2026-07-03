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
