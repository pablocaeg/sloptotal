# SlopTotal: Architectural Investigation & Next Steps

**Date**: February 2026
**Status**: Active investigation — decisions documented for implementation
**Companion doc**: `docs/INVESTIGATIONS.md` (benchmark data, scoring evolution)

---

## 1. The Objective

Make SlopTotal's Chrome extension a **reliable AI content indicator for any webpage** — not just for 2023-era cliché-ridden content farms.

**Constraints:**
- Zero external API costs (all local inference)
- No significant performance regression (Phase 1: <400ms, Phase 2: <3s)
- Use models we already have loaded in memory
- Works on real-world text extracted from any website

---

## 2. What We Have (Asset Inventory)

### 2.1 Models Already Loaded

| Model | Size | Used In | Loaded When | Batch? |
|-------|------|---------|-------------|--------|
| BERT-base (RAID) | 4.4M | Snippet scan, quick-score | App startup | Yes |
| E5-base (RAID) | 33M | Snippet scan, quick-score | App startup | Yes |
| RoBERTa-base (TMR) | 125M | Snippet scan, quick-score | App startup | Yes |
| RoBERTa-base (Fakespot) | 125M | Snippet scan, quick-score | App startup | Yes |
| **GPT-2 Large** | 774M | Full analysis (6 engines share) | First full analysis | No (cached) |
| DistilGPT-2 | 82M | CrossPerplexity (full analysis) | First full analysis | No (cached) |
| ReMoDetect reward model | ~125M | Full analysis only | First full analysis | No |

**Key insight**: GPT-2 Large is our most powerful unused asset. It's loaded for full analysis but never used in URL scans. A single forward pass (~100ms on CPU for 500 tokens) feeds 6 different engines through `gpt2_cache.py`.

### 2.2 Existing Infrastructure

| Component | What It Does | Available In |
|-----------|-------------|--------------|
| `gpt2_cache.py` | Single forward pass → per-token logits shared by 6 engines | Full analysis only |
| `BurstinessEngine` | Per-sentence perplexity CV from GPT-2 | Full analysis only |
| `DivEyeEngine` | Surprisal CV + skewness from GPT-2 | Full analysis only |
| `GLTREngine` | Token rank distribution from GPT-2 | Full analysis only |
| `LogRankEngine` | Normalized log-rank from GPT-2 | Full analysis only |
| `FastDetectGPTEngine` | Perturbation-free detectGPT from GPT-2 | Full analysis only |
| `scraper.py` | Fetches raw HTML, extracts text via trafilatura | URL scans |
| `PageContent` dataclass | Splits text: 500ch ML + 4000ch heuristic | URL scans |
| Extension content script | Has full DOM access on every page | Extension only |
| `analyze_page_structure()` | 6 heuristic regex engines on 4000ch | URL scans |
| `_blend_url_scores()` | Guard-aware ML + structural blending | URL scans |

### 2.3 Engine Tiers (Full Analysis)

| Tier | Engines | Method | Relevance to URL Scans |
|------|---------|--------|----------------------|
| A: Neural classifiers | BERT-RAID, E5, TMR, Fakespot | Fine-tuned transformers | Already used (4-engine snippet scan) |
| B: Zero-shot statistical | Binoculars, LLR, Intrinsic Dim | Novel metrics from model internals | Too slow for URL scans |
| C: GPT-2 derived | GLTR, LogRank, DivEye, FastDetectGPT, Burstiness | Per-token analysis from cached GPT-2 pass | **Available if we add GPT-2 to URL scans** |
| D: Reward model | ReMoDetect | Reward signal as proxy | Slow (~2s), but powerful on long text |
| E: Heuristic | Linguistic, Formulaic, Structural, etc. | Regex/stats | Already used (6-engine structural analysis) |

---

## 3. What We've Learned

### 3.1 The Formality Problem (Unsolvable by Tier A)

All 4 fast classifiers detect **formality**, not AI authorship. Formal human text (news, Wikipedia, business writing) and formal AI text produce statistically identical scores.

```
              BERT   E5    TMR   Fakespot
Formal Human: 0.90+ 0.85+ 0.93+ 0.90+
Formal AI:    0.90+ 0.88+ 0.95+ 0.93+
Gap:          ~0.00 ~0.03 ~0.02 ~0.03
```

**Current mitigation**: Formal Text Guard (fakespot ≥ 0.90 AND tmr ≥ 0.93) → cap at 55% yellow. This prevents false reds but creates a ceiling where we can't distinguish formal AI from formal human.

### 3.2 Heuristic Engine Upgrade Results

We upgraded 3 heuristic engines (structural.py, formulaic.py, sentiment.py) to detect modern AI patterns — colon density, colon-introduced definitions, explanatory "this/these" patterns, sentence starter repetition.

**What worked:**
- Colon density (>8/1k words) — strong discriminator for content-farm AI
- Colon-introduced definitions ("Term: Explanation") — strong, near-zero in human text
- New structural composite weights (colon signals at 0.30 each)

**What failed:**
- Sentence starter repetition — no separation between AI (57-63%) and human (21-62%). Effectively disabled (threshold 0.55, weight 0.05).
- Heading → bullet-list detection — trafilatura strips HTML structure, lists arrive as continuous text. Signal rarely fires.
- "This/these" explanatory pattern — fires 0-2x per page, below the threshold of 4 needed to register as meaningful.

**Net result:**
- AI content farms: heuristic composite 6-8% → 27-41% (improvement)
- Human text: stays at 5-17% (no false positives)
- **But**: These signals are format-specific (Term: Definition lists), not general AI detection

### 3.3 The trafilatura Bottleneck

trafilatura is excellent at extracting article text but **destroys structural information**:
- HTML lists become single-line text
- Headings lose their hierarchy
- Formatting (bold, bullet points) stripped
- Multi-paragraph articles sometimes collapse to 1-3 text blocks

This kills 3 of our 6 heuristic engines (list density, heading→list, format density typically return 0).

### 3.4 What Actually Discriminates AI from Human Text

Based on all testing, ranked by reliability:

| Signal | Reliability | Available In | Notes |
|--------|------------|-------------|-------|
| Per-sentence perplexity CV | High (untested at scale) | Full analysis only | Low CV = flat AI rhythm; high CV = natural human variation |
| Token rank distribution (GLTR) | High | Full analysis only | AI text uses more top-10 and top-100 tokens |
| Surprisal variance (DivEye) | Medium-High | Full analysis only | Low skewness = AI's predictable patterns |
| Colon density + definitions | Medium (format-specific) | URL scans | Strong for Term:Definition AI style |
| 4-engine classifier consensus | Medium (formal text blind) | Snippet + URL scans | Works for casual text, fails on formal |
| Normalized log-rank | Medium | Full analysis only | Lower mean = more predictable = AI |
| Hedging phrase density | Low-Medium | URL scans | 2023-era AI clichés declining |
| Formulaic openers/closers | Low | URL scans | Almost extinct in modern AI |

**The pattern is clear**: The most reliable signals (perplexity CV, token ranks, surprisal variance) all come from GPT-2 and are currently locked behind the full analysis pipeline.

---

## 4. Architectural Decision: Bring GPT-2 to URL Scans

### 4.1 The Key Insight

We already pay the cost of a GPT-2 Large forward pass in full analysis. The infrastructure (`gpt2_cache.py`) already caches per-token logits so 6 engines can share one pass. The **only reason** GPT-2 signals aren't in URL scans is that nobody wired it up.

A single GPT-2 forward pass on 500 tokens costs ~100-150ms on CPU. URL scans already take 2-3 seconds (dominated by HTTP fetch). Adding 150ms is negligible.

### 4.2 What One GPT-2 Pass Gives Us

From a single `get_gpt2_outputs(text)` call, we can extract:

1. **Burstiness (per-sentence perplexity CV)**: The most promising discriminator. AI text has flat, uniform sentence-level perplexity (CV ~0.15). Human text is bursty (CV ~0.50-0.80). This measures something fundamentally different from the classifier-based engines — it measures the predictability pattern of the text itself, not what it "looks like" to a trained classifier.

2. **GLTR token ranks**: Percentage of tokens in top-10, top-100, top-1000 of GPT-2's predictions. AI text clusters heavily in top-10/100 (predictable tokens). Human text has more surprise tokens. This is well-established in the literature.

3. **DivEye surprisal statistics**: CV and skewness of per-token surprisal (negative log-probability). AI text has low CV (uniform surprisal) and near-zero skewness. Human text has high CV and positive skewness (occasional very surprising words).

4. **Log-rank mean**: Average normalized rank position of each token. Lower = more predictable = more likely AI.

5. **Overall perplexity (loss)**: Direct cross-entropy loss. Lower = text is more predictable by GPT-2 = more likely AI-generated. Simple but effective baseline.

### 4.3 Cost Analysis

| Component | Current URL Scan | With GPT-2 Added |
|-----------|-----------------|------------------|
| HTTP fetch | ~800-1500ms | ~800-1500ms |
| 4-engine ML (BERT/E5/TMR/Fakespot) | ~120ms | ~120ms |
| 6 heuristic engines | ~5ms | ~5ms |
| GPT-2 forward pass | — | ~100-150ms |
| GPT-2 signal extraction | — | ~10-20ms |
| **Total** | **~1.0-1.7s** | **~1.1-1.9s** |

HTTP fetch dominates. GPT-2 adds <15% to total latency.

### 4.4 Implementation Plan

#### Phase A: GPT-2 Perplexity Signals in URL Scans

**Goal**: Add burstiness (perplexity CV) + overall perplexity to the URL scan pipeline alongside existing ML + heuristic scoring. This gives us the single most promising discriminator without requiring full analysis.

**Changes:**

1. **`app/analyzer.py`** — New function: `compute_gpt2_signals(text: str) -> dict`
   - Call `get_gpt2_outputs(text)` (already cached/shared)
   - Extract per-sentence perplexity CV (burstiness logic)
   - Extract overall loss (perplexity)
   - Extract GLTR-style token rank percentages
   - Return: `{"burstiness_cv": float, "perplexity": float, "top10_pct": float, "top100_pct": float}`
   - Runs in thread pool executor (GPT-2 is CPU-bound, already thread-safe via lock in gpt2_cache)

2. **`app/analyzer.py`** — Modify `_blend_url_scores()`:
   - Accept new parameter: `gpt2_signals: dict | None`
   - When guard hits AND burstiness CV is low (<0.25): strong AI signal despite formal text → allow score to reach 70-75%
   - When guard hits AND burstiness CV is high (>0.50): confirmed formal human → strengthen cap at 45%
   - When no guard: use burstiness as a third scoring dimension alongside ML and heuristic

3. **`app/routes/api.py`** — Modify URL scan endpoint:
   - After fetching page content, run GPT-2 signals in parallel with ML + heuristic
   - Pass results to `_blend_url_scores()`
   - Include in response for extension detail panel

4. **`app/engines/gpt2_cache.py`** — No changes needed. Already handles concurrent access, caching, and cleanup.

**Risk**: GPT-2 model load time (~3-5s) on first URL scan if no full analysis has been run yet. Mitigation: Pre-warm GPT-2 during app startup lifespan (load it eagerly alongside the 4 fast classifiers).

#### Phase B: HTML Structure Extraction (Before trafilatura)

**Goal**: Parse HTML for structural features (lists, headings, sections) before trafilatura strips them.

**Changes:**

1. **`app/scraper.py`** — New function: `extract_html_features(html: str) -> dict`
   - Use stdlib `html.parser` or BeautifulSoup (already a trafilatura dependency) to count:
     - `<ul>/<ol>` lists and their `<li>` counts
     - `<h1>`-`<h6>` headings
     - `<table>` elements
     - Section patterns (heading → list → heading → list)
     - Bold/emphasis density
   - Return: `{"list_count": int, "list_items": int, "headings": int, "heading_list_sections": int, "tables": int}`
   - Cost: ~2ms (DOM parse is fast)

2. **`app/scraper.py`** — Modify `PageContent` dataclass:
   - Add `html_features: dict` field
   - Populate from `extract_html_features(html)` in `extract_text_with_metadata()`

3. **`app/analyzer.py`** — Feed HTML features into heuristic analysis:
   - The structural and formulaic engines can use HTML-derived counts instead of trying to detect lists/headings in flattened text

**Impact**: Unblocks 3 currently-dead heuristic signals (list density, heading→list, format density).

#### Phase C: Extension DOM Fingerprinting

**Goal**: Extract structural features client-side where the DOM is intact and no extraction artifacts exist.

**Changes:**

1. **`extension/content.js`** — New function: `extractDOMFeatures(element)`
   - For each search result's target page (when user navigates), extract:
     - List item count, heading count, section structure
     - Content-to-boilerplate ratio
     - Paragraph count and length distribution
   - Send features alongside URL in phase-2 scan request

2. **`extension/background.js`** — Include DOM features in `/api/scan/urls` request

3. **API** — Accept optional `dom_features` in URL scan request, pass to heuristic analysis

**This is complementary to Phase B**: Phase B works server-side on fetched HTML, Phase C works client-side on rendered DOM. Phase C is more accurate (sees the final rendered state) but only available in the extension.

---

## 5. Priority Order

| Priority | Phase | Effort | Impact | Rationale |
|----------|-------|--------|--------|-----------|
| **1** | **A: GPT-2 signals** | Medium (1-2 days) | High | The burstiness CV is fundamentally different from classifier-based detection. It measures text predictability patterns, not "what formal text looks like." This directly attacks the formality problem. |
| **2** | **B: HTML features** | Small (hours) | Medium | Unblocks dead heuristic signals. Quick win — we already have the HTML string, just need to parse it before trafilatura. |
| **3** | **C: Extension DOM** | Medium (1 day) | Medium | Best structural data source, but only available in extension. Phase B covers the server-side case. |

**Phase A is the clear priority** because it provides a fundamentally new signal type (statistical predictability) that doesn't share the formality confound of our classifiers. The BurstinessEngine already implements the exact logic we need — we just need to wire it into the URL scan pipeline.

---

## 6. Expected Outcomes

### With Phase A (GPT-2 Signals)

**Formal text disambiguation**: The guard currently caps formal text at 55% (can't tell if AI or human). With burstiness CV:
- Formal human text (Wikipedia, news): high CV (0.40-0.80) → confirm human, lower cap to 40-45%
- Formal AI text (content farms): low CV (0.10-0.25) → break through guard, score 65-75%

This is the **single biggest improvement** we can make.

**Casual AI detection**: BurstinessEngine may also help with casual AI (which evades classifiers). Even when AI mimics casual style, the underlying perplexity pattern may still be detectable. This is untested and needs validation.

### With Phase B (HTML Features)

- Content-farm AI with heavy list formatting: heuristic score jumps from ~30% to ~50-60%
- Human text: no regression (humans don't structure pages as Term: Definition lists)
- Works for ALL URL scans, not just extension

### Combined

The three-signal blend (ML classifiers + GPT-2 stats + heuristic/structural) gives us three independent measurement dimensions:
1. **What does it look like?** (classifiers — detects formality)
2. **How predictable is it?** (GPT-2 — detects generation patterns)
3. **How is it formatted?** (heuristics — detects AI formatting conventions)

No single dimension is sufficient. All three together provide much more robust detection.

---

## 7. What This Won't Solve

Being honest about limitations:

1. **Short snippets (<150ch)** remain unreliable. GPT-2 needs ~50+ tokens for meaningful perplexity estimates. Snippets are too short.

2. **Casual AI mimicking human style** with varied sentence structure — if the perplexity CV is also high (bursty), we have no signal. This requires validation.

3. **Adversarial evasion** — a determined adversary who knows our signals can craft text that defeats all three dimensions. This is true of all AI detection.

4. **Non-English text** — all models are English-trained. Non-English text will score unreliably.

5. **Mixed content** (human-edited AI, AI-assisted human) — fundamentally ambiguous. No detection system can reliably handle this.

---

## 8. Validation Plan

Before deploying any changes:

1. **Collect GPT-2 burstiness baselines** on current test URLs (3 AI farms + 12 human sites) using the existing BurstinessEngine logic
2. **Measure separation**: If AI CV < 0.25 and Human CV > 0.40 consistently, we have a usable signal
3. **Test formal text specifically**: Wikipedia articles, BBC news, business pages — must have high CV (human-like)
4. **Test modern AI specifically**: Fresh ChatGPT/Claude outputs on various topics — must have low CV
5. **Build a larger validation set**: At least 30 AI + 30 human texts from diverse sources
6. **A/B test blending weights**: Run both old and new scoring in parallel, log both, compare

---

*This document captures architectural decisions for the SlopTotal project. Implementation begins with Phase A (GPT-2 signals in URL scans).*
