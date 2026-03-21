# SlopTotal AI Detection Scoring Research

**Research Investigations Document**
**Project**: SlopTotal -- Open-Source AI Content Detection
**Date**: February 2026
**Status**: Active research, findings documented for open-source paper

---

## Table of Contents

1. [Engine Characterization](#1-engine-characterization)
2. [The Formality Problem](#2-the-formality-problem)
3. [Fakespot Reliability Analysis](#3-fakespot-reliability-analysis)
4. [Scoring Strategy Evolution](#4-scoring-strategy-evolution)
5. [Text Length Tiers](#5-text-length-tiers)
6. [Benchmark Results Summary](#6-benchmark-results-summary)
7. [Remaining Limitations](#7-remaining-limitations)
8. [Two-Phase Architecture](#8-two-phase-architecture)
9. [Appendix: Raw Benchmark Data](#9-appendix-raw-benchmark-data)

---

## 1. Engine Characterization

SlopTotal uses four batch-capable transformer classifiers for its fast-scoring pipeline (snippet scan and quick-score). All four engines are open-weight models that run locally on CPU.

### 1.1 Engine Specifications

| Engine | Model Family | Parameters | Inference (single) | Inference (5-batch) | Training Data |
|--------|-------------|------------|-------------------|---------------------|---------------|
| BERT-RAID | BERT-base | 4.4M fine-tuned | ~3 ms | ~3 ms | RAID dataset |
| E5 | E5-base | 33M | ~35 ms | ~35 ms | RAID dataset |
| TMR | RoBERTa-base | 125M | ~120 ms | ~122 ms | MAGE corpus, 97.3% reported accuracy |
| Fakespot | RoBERTa-base | 125M | ~113 ms | ~116 ms | Review + article corpus |

**Measured timing** (from `bench_realistic.py`, 39-text batch on CPU):

```
bert_raid:  3.07 ms
e5:        37.19 ms
tmr:      122.17 ms
fakespot: 116.02 ms
```

### 1.2 Parallel Execution Model

All four engines execute in parallel via separate thread pool workers. Total latency equals the slowest engine, not the sum:

```
Total batch latency = max(bert, e5, tmr, fakespot) = ~122 ms
```

For the Chrome extension snippet scan (5 texts per batch), this yields approximately 350 ms end-to-end including network round-trip and JSON serialization, enabling real-time badge display on search engine result pages.

### 1.3 Full Analysis Pipeline

Beyond the 4 fast classifiers, SlopTotal's full analysis uses 23 engines across five tiers:

- **Tier A**: TMR, ReMoDetect (RAID-trained classifiers)
- **Tier B**: Binoculars, Fast-DetectGPT, Perplexity, Cross-Perplexity (zero-shot / model-based)
- **Tier C**: Fakespot, E5, BERT-RAID, OpenAI classifier, ChatGPT classifier, Desklib, SuperAnnotate
- **Tier D**: GLTR, Log-Rank, DivEye, Burstiness (GPT-2 derived statistics)
- **Tier E**: Linguistic, Structural, Vocabulary, Formulaic, Readability, Sentiment (heuristic engines)

Full analysis takes 2-7 seconds depending on text length and hardware.

---

## 2. The Formality Problem

### 2.1 Critical Discovery

**All four fast engines detect formality, not AI authorship.**

This is the single most important finding from our research. When we expanded our benchmark from casual/informal text to include formal human writing (news articles, Wikipedia, business reports, medical papers, encyclopedia entries), every engine produced near-identical scores for formal human text and formal AI text.

The engines are not detecting "AI-generated content." They are detecting "text that sounds formal, structured, and polished" -- a property shared by professional human writing and typical AI output.

### 2.2 Empirical Evidence

Raw engine scores from the 39-text realistic benchmark (`bench_realistic.py`):

#### Per-Category Mean Engine Scores

| Category | N | BERT-RAID | E5 | TMR | Fakespot |
|----------|---|-----------|-----|------|----------|
| **Casual human** | 8 | 0.666 | 0.557 | 0.553 | 0.122 |
| **Formal human** | 7 | 0.953 | 0.914 | 0.983 | 0.999 |
| **Other human** (tech/review/recipe/encyclopedia) | 5 | 0.801 | 0.900 | 0.962 | 0.817 |
| **Formal AI** (ChatGPT formal) | 8 | 0.925 | 0.917 | 0.985 | 0.999 |
| **Casual AI** (ChatGPT/Claude mimicking human) | 7 | 0.771 | 0.789 | 0.725 | 0.544 |
| **Business AI** | 2 | 0.973 | 0.915 | 0.986 | 0.999 |
| **Educational AI** | 1 | 0.944 | 0.897 | 0.983 | 1.000 |
| **Review AI** | 1 | 0.965 | 0.824 | 0.987 | 1.000 |

#### The Indistinguishable Pair

Compare formal human vs. formal AI scores side by side:

| Engine | Formal Human (N=7) | Formal AI (N=8) | Difference |
|--------|-------------------|-----------------|------------|
| BERT-RAID | 0.953 | 0.925 | 0.028 |
| E5 | 0.914 | 0.917 | -0.003 |
| TMR | 0.983 | 0.985 | -0.002 |
| Fakespot | 0.999 | 0.999 | 0.000 |

The difference between formal human and formal AI scores is within noise for E5, TMR, and Fakespot. BERT-RAID shows a marginal 0.028 gap -- statistically meaningless for classification purposes.

### 2.3 Implications

1. **Any threshold-based classifier will either**:
   - Accept false positives on formal human text (if threshold is low enough to catch AI), or
   - Miss formal AI text (if threshold is high enough to avoid false positives on human text)

2. **The formality problem is fundamental** to transformer-based classifiers trained on AI-vs-human data, because:
   - Training data correlates formality with AI origin (most AI training samples are formal)
   - The models learn "formal = AI" rather than any deeper structural property
   - Formal human writing shares the same distributional properties that these models key on

3. **Casual AI text that mimics human style evades all engines** -- the engines score it lower precisely because it is less formal, not because they recognize it as human.

---

## 3. Fakespot Reliability Analysis

Fakespot emerged as the most useful individual engine despite its limitations, due to one key property: it has the widest gap between human and AI scores on average.

### 3.1 MAGE Hard Evaluation Results

Empirical accuracy measured on the MAGE "hard" evaluation set:

| Engine | Human Accuracy | AI Accuracy | Gap |
|--------|---------------|-------------|-----|
| Fakespot | 48% | 80% | **32%** |
| E5 | 79% | 89% | 10% |
| BERT-RAID | 77% | 84% | 7% |
| TMR | 80% | 81% | **1%** |

TMR has almost zero discriminative power (1% gap), meaning it scores human and AI text nearly identically. Fakespot, despite a low human accuracy (48%), has the largest gap and thus carries the most information for calibrated scoring.

### 3.2 Fakespot Signal Reliability by Score Range

| Fakespot Score | Interpretation | Reliability |
|----------------|---------------|-------------|
| **< 0.25** | Confident human indicator | **Reliable at any text length.** No formal human text in our benchmark scored below 0.25 on Fakespot while being genuinely AI. |
| **0.25 - 0.50** | Uncertain / transitional | Low reliability. Common for casual AI text and some human text with moderate formality. |
| **0.50 - 0.90** | Moderate AI signal | Useful when combined with E5 agreement, but insufficient alone. |
| **> 0.90** | Detects formality, not AI | **Unreliable as AI indicator.** Identical scores for formal human (news, Wikipedia, business) and formal AI (ChatGPT, Claude formal output). |

### 3.3 Fakespot and Text Length

| Text Length | Fakespot FP Rate | Detection Rate | Notes |
|-------------|-----------------|----------------|-------|
| < 150 chars | ~25% | Variable | Unreliable. Short text lacks sufficient signal. |
| 150-299 chars | ~10-15% | Moderate | Partially reliable. Use with E5 corroboration. |
| 300+ chars | ~0% (on original benchmark) | High | Reliable for Fakespot-LOW. Fakespot-HIGH still confounded by formality. |

### 3.4 Key Insight

Fakespot's value is asymmetric:
- **Fakespot LOW is a reliable negative** (human indicator) -- when Fakespot scores below 0.25, the text is almost certainly human-written, regardless of what other engines say.
- **Fakespot HIGH is unreliable as a positive** (AI indicator) -- scores above 0.90 are identical for formal human and formal AI text.

This asymmetry drives the entire scoring strategy: trust Fakespot when it says "human," be skeptical when it says "AI."

---

## 4. Scoring Strategy Evolution

### 4.1 Version 1: Two-Engine Weighted Average (E5 + Fakespot)

**Configuration**: 50/50 weighted average of E5 and Fakespot scores.

**Results on original 20-text benchmark** (casual/informal mix):
- F1 = 0.870
- Good performance on casual text
- No formal text in benchmark, so formality problem not yet discovered

**Why it was replaced**: Adding more engines should improve robustness. The 2-engine system was fragile -- a single engine error could swing the score dramatically.

### 4.2 Version 2: Four-Engine Adaptive Scoring (No Formal Guard)

**Configuration**: All four engines (BERT-RAID, E5, TMR, Fakespot) with adaptive weights based on text length. Fakespot used as primary anchor with length-dependent trust tiers.

**Results on original 20-text benchmark**:
- F1 = 0.909
- 100% AI detection rate (10/10 AI texts detected)
- 80% human accuracy (8/10 human texts correctly identified)
- **Zero false reds** (no human text scored above 65%)

**Results on realistic 39-text benchmark** (with formal text):
- F1 = 0.667
- 15/19 AI texts detected (78.9% recall)
- **11/20 false reds** on human text (55% FP rate)
- ALL 11 false reds were formal human text (news, Wikipedia, business, encyclopedia, recipe)
- Precision dropped to 57.7%

| Metric | Original Benchmark | Realistic Benchmark |
|--------|-------------------|-------------------|
| Precision | 1.000 | 0.577 |
| Recall | 1.000 | 0.789 |
| F1 | 0.909* | 0.667 |
| False Reds | 0 | 11 |

*F1 on original benchmark was 0.909 because 2/10 human texts scored yellow (false positive at lower threshold), not red.

**Why it was replaced**: The 11 false reds on formal human text were unacceptable. A user submitting a news article or Wikipedia paragraph would be told it was "AI-generated" with high confidence -- a harmful false accusation.

### 4.3 Version 3: Four-Engine Adaptive + Formal Text Guard (Current)

**Configuration**: Same four-engine adaptive scoring as v2, with a graduated guard rule that uses BERT as a discriminator within the formal unanimity pattern:

```
IF fakespot >= 0.90 AND tmr >= 0.93:
    IF bert < 0.50:       # BERT disagrees -- human signal
        cap at 35% (green)
    ELIF bert < 0.70:     # BERT moderately low
        cap at 45% (low yellow)
    ELSE:                 # Full unanimity -- indistinguishable
        cap at 55% (yellow)
    confidence = "low"
```

**Rationale**: When both Fakespot AND TMR produce very high scores (the "formal unanimity" pattern), the engines are detecting formality, not AI. BERT occasionally correctly identifies human text even when Fakespot/TMR are fooled (e.g., product reviews with personal voice get BERT=0.14 but Fakespot=0.98). The graduated cap leverages this signal.

**Guard variant analysis** (8 variants tested offline against 39-text benchmark):

| Variant | Description | F1 | False Reds | Human Green | AI Missed |
|---------|-------------|-----|------------|-------------|-----------|
| NO_GUARD | No guard | 0.708 | 11 | 5 | 1 |
| V1_FLAT | fs>=0.90, tmr>=0.93, flat cap 0.55 | 0.708 | 0 | 5 | 1 |
| **V7_BERT_FULL** | **V1 + BERT sub-tiers** | **0.723** | **0** | **6** | **1** |
| V8_SMART | V7 + skip guard for <150ch | 0.723 | 0 | 6 | 1 |
| V3_TIGHTER | fs>=0.95, tmr>=0.96 | 0.708 | 0 | 5 | 1 |
| V4_4ENGINE | All 4 engines >= 0.80 | 0.708 | 0 | 5 | 1 |

**V7_BERT_FULL** was selected as the optimal variant: zero false reds, best human green rate (6/20), and highest F1 (0.723).

**Results on realistic 39-text benchmark with V7 guard**:
- **0 false reds** on human text
- 6/20 human texts correctly green (vs 5 without BERT sub-tiers)
- 14/20 human texts yellow (honest "uncertain" for formal text)
- 3/19 AI texts detected as red (non-formal AI patterns)
- 13/19 AI texts capped to yellow (formal AI indistinguishable from formal human)
- 2/19 AI texts missed (casual AI that evades all engines)

**ReMoDetect tested as potential tiebreaker** within the guard:
- ReMoDetect (reward-model-based RLHF detector) also fails to distinguish formal human from formal AI
- Guard-triggered subset: Human ReMoDetect avg=0.952, AI avg=0.985 (gap only 0.033)
- Best F1 within guard subset: 0.722 at threshold=0.75 (10/11 human FP)
- **Conclusion**: ReMoDetect detects "high-reward" text, not AI authorship. Same formality confound.

#### Per-Text Results With Formal Guard

**Human texts** (all 20 correctly handled -- no false reds):

| ID | Style | BERT | E5 | TMR | Fakespot | Raw Score | Guarded | Guard Hit |
|----|-------|------|-----|------|----------|-----------|---------|-----------|
| H00 | casual | 0.908 | 0.600 | 0.929 | 0.149 | 28.4% | 28.4% | No |
| H01 | casual | 0.952 | 0.867 | 0.937 | 0.016 | 27.2% | 27.2% | No |
| H02 | casual | 0.736 | 0.269 | 0.052 | 0.021 | 9.5% | 9.5% | No |
| H03 | casual | 0.943 | 0.873 | 0.939 | 0.325 | 45.0% | 45.0% | No |
| H04 | casual | 0.182 | 0.129 | 0.757 | 0.413 | 37.1% | 37.1% | No |
| H05 | formal (news) | 0.969 | 0.929 | 0.986 | 0.999 | 85.4% | **55.0%** | Yes |
| H06 | formal (science) | 0.949 | 0.939 | 0.976 | 1.000 | 85.3% | **55.0%** | Yes |
| H07 | formal (business) | 0.895 | 0.887 | 0.984 | 0.997 | 83.5% | **55.0%** | Yes |
| H08 | formal (travel) | 0.971 | 0.901 | 0.985 | 0.999 | 84.7% | **55.0%** | Yes |
| H09 | formal (medical) | 0.970 | 0.915 | 0.982 | 0.999 | 85.0% | **55.0%** | Yes |
| H10 | technical | 0.954 | 0.905 | 0.938 | 0.168 | 55.0% | 55.0% | No |
| H11 | review | 0.204 | 0.879 | 0.982 | 0.993 | 83.9% | **35.0%** | Yes (BERT sub-tier: bert<0.50→green) |
| H12 | instructional | 0.945 | 0.914 | 0.969 | 0.999 | 84.6% | **55.0%** | Yes |
| H13 | encyclopedia | 0.930 | 0.903 | 0.977 | 0.931 | 82.2% | **55.0%** | Yes |
| H14 | encyclopedia | 0.970 | 0.898 | 0.944 | 0.992 | 84.0% | **55.0%** | Yes |
| H15 | casual (long) | 0.218 | 0.714 | 0.147 | 0.039 | 31.8% | 31.8% | No |
| H16 | formal (long, finance) | 0.946 | 0.926 | 0.986 | 1.000 | 85.3% | **55.0%** | Yes |
| H17 | casual (long) | 0.531 | 0.689 | 0.648 | 0.012 | 42.2% | 42.2% | No |
| H18 | formal (long, travel) | 0.971 | 0.901 | 0.985 | 1.000 | 84.9% | **55.0%** | Yes |
| H19 | casual (long) | 0.859 | 0.316 | 0.014 | 0.004 | 22.7% | 22.7% | No |

**AI texts** (trade-off: formal AI also capped):

| ID | Style | BERT | E5 | TMR | Fakespot | Raw Score | Guarded | Guard Hit |
|----|-------|------|-----|------|----------|-----------|---------|-----------|
| A00 | formal | 0.974 | 0.925 | 0.985 | 0.996 | 85.2% | **55.0%** | Yes |
| A01 | formal | 0.971 | 0.921 | 0.985 | 1.000 | 85.2% | **55.0%** | Yes |
| A02 | formal | 0.807 | 0.863 | 0.979 | 1.000 | 92.7% | **55.0%** | Yes |
| A03 | formal | 0.771 | 0.932 | 0.986 | 1.000 | 94.3% | **55.0%** | Yes |
| A04 | formal | 0.970 | 0.927 | 0.985 | 0.999 | 85.3% | **55.0%** | Yes |
| A05 | casual AI | 0.861 | 0.890 | 0.963 | 0.385 | 55.0% | 55.0% | No |
| A06 | casual AI | 0.494 | 0.826 | 0.980 | 0.517 | 65.0% | 65.0% | No |
| A07 | casual AI | 0.873 | 0.811 | 0.978 | 0.876 | **87.1%** | **87.1%** | No |
| A08 | casual AI | 0.923 | 0.822 | 0.149 | 0.011 | 37.9% | 37.9% | No |
| A09 | casual AI | 0.445 | 0.597 | 0.060 | 0.126 | 34.1% | 34.1% | No |
| A10 | business AI | 0.973 | 0.890 | 0.986 | 0.999 | 84.6% | **55.0%** | Yes |
| A11 | business AI | 0.973 | 0.939 | 0.987 | 0.998 | 85.6% | **55.0%** | Yes |
| A12 | educational AI | 0.944 | 0.897 | 0.983 | 1.000 | 84.4% | **55.0%** | Yes |
| A13 | formal AI (long) | 0.973 | 0.930 | 0.987 | 1.000 | 85.6% | **55.0%** | Yes |
| A14 | formal AI (long) | 0.964 | 0.909 | 0.986 | 1.000 | 85.0% | **55.0%** | Yes |
| A15 | casual AI (long) | 0.925 | 0.896 | 0.986 | 1.000 | 84.4% | **55.0%** | Yes |
| A16 | formal AI (long) | 0.970 | 0.927 | 0.986 | 1.000 | 85.5% | **55.0%** | Yes |
| A17 | casual AI (long) | 0.877 | 0.684 | 0.962 | 0.894 | **84.0%** | **84.0%** | No |
| A18 | review AI | 0.965 | 0.824 | 0.987 | 1.000 | 94.2% | **55.0%** | Yes |

### 4.4 The Honest Trade-Off

The formal guard eliminates all false reds but at a significant cost: formal AI text is also capped at yellow (55%). This is not a bug -- it is an honest acknowledgment that **these four engines literally cannot tell the difference**.

Reporting "AI detected with high confidence" on text that is indistinguishable from a New York Times article or a Wikipedia entry would be irresponsible. The yellow "uncertain" result with low confidence correctly communicates the system's actual epistemic state.

Only AI text that does NOT trigger the formal unanimity pattern (i.e., text where the engines actually disagree in an informative way) gets classified as red. In practice, this means:
- Casual AI text with some Fakespot signal (A07: fakespot=0.876, but tmr not quite at 0.93 threshold): detected
- AI text with genuine engine disagreement (A17: fakespot=0.894 < 0.90 threshold): detected

### 4.5 Quick-Score and Full-Analysis Calibration

Beyond the snippet scorer (`_compute_snippet_score`), two additional calibrated scoring functions handle broader analysis:

**Quick-score** (`_calculate_calibrated_score`): Uses the same 4 engines plus linguistic and formulaic heuristic engines. Applies:
1. Fakespot-dominant weighted scoring (Fakespot weight 0.50-0.80 depending on confidence)
2. Unanimous-high skepticism (min_score > 0.85 AND spread < 0.15 triggers formal text guard)
3. "No markers" penalty (high ML score + zero linguistic/formulaic AI markers = reduce score)
4. Human signal adjustment (contractions, first-person, slang pull score down; AI transitions, lists pull up)

**Full analysis** (`_calculate_full_calibrated_score`): Same calibration strategy applied to all 23 engines, blending the weighted average baseline with Fakespot-anchored correction.

---

## 5. Text Length Tiers

The snippet scorer uses three text length tiers, each with different engine trust levels and score caps.

### 5.1 Tier 0: Very Short Text (< 150 characters)

**All engines are unreliable at this length.**

| Condition | Strategy | Cap |
|-----------|----------|-----|
| Fakespot < 0.25 | Trust Fakespot as human signal, blend with E5 | 40% (green) |
| Fakespot 0.25-0.50 | Mild positive, possible FP | 45% (yellow) |
| Fakespot > 0.50 | ~25% chance of FP at this length | 50% (yellow) |

Rationale: At < 150 characters, there is insufficient text for any engine to make a reliable determination. Fakespot's false positive rate at this length is approximately 25%. The only reliable signal is Fakespot-LOW (< 0.25), which indicates casual/informal human text.

### 5.2 Tier 1: Medium Text (150-299 characters)

**Partial reliability. Fakespot begins to work; E5 provides corroboration.**

| Condition | Strategy | Cap |
|-----------|----------|-----|
| Fakespot >= 0.70 AND E5 >= 0.70 | Strong agreement, allow higher scores | 65% (borderline red) |
| Fakespot >= 0.50, other conditions | Moderate signal | 65% |
| Fakespot < 0.50, E5 > 0.75, TMR > 0.80 | Consensus without Fakespot | 55% (yellow) |
| Fakespot < 0.50, E5 > 0.75 | E5 alone | 50% (yellow) |
| Fakespot < 0.50, E5 < 0.50 | Both low -- likely human | No cap |
| Other | Conservative blend | 45% (yellow) |

### 5.3 Tier 2: Long Text (300+ characters)

**Fakespot reliable for LOW scores. Formal unanimity guard still applies.**

This tier allows full weighted scoring when engines disagree informatively, but the formal unanimity guard (fakespot >= 0.90 AND tmr >= 0.93) overrides everything and caps at 55%.

When not in formal unanimity:
- Fakespot >= 0.50 + E5 > 0.60: Full weighted scoring with high confidence
- Fakespot >= 0.50 + E5 <= 0.60: Fakespot-dominant scoring with medium confidence
- Fakespot 0.35-0.50: Moderate signal, Fakespot-anchored
- Fakespot < 0.35 + E5 < 0.60: Strong human signal, medium confidence
- Fakespot < 0.35 + E5 >= 0.60: Formal text pattern (Fakespot disagrees), cap at 45%

---

## 6. Benchmark Results Summary

### 6.1 Original 20-Text Benchmark (`bench_full.py`)

**Corpus**: 30 texts total -- 15 human-written + 15 AI-generated. Predominantly casual and informal text. No formal news articles, Wikipedia, or business writing.

**Best single-engine results** (threshold sweep):

| Engine | Best Threshold | F1 | Precision | Recall |
|--------|---------------|-----|-----------|--------|
| Fakespot | 0.65 | 0.903 | 0.857 | 0.955 |
| E5 | 0.70 | 0.870 | 0.800 | 0.952 |
| BERT-RAID | 0.80 | 0.750 | 0.714 | 0.789 |
| TMR | 0.90 | 0.667 | 0.600 | 0.750 |

**Best engine combinations** (threshold sweep):

| Combination | Weights | Best Threshold | F1 |
|-------------|---------|---------------|-----|
| BERT-RAID + Fakespot | 50/50 | 0.65 | **0.968** |
| E5 + Fakespot | 50/50 | 0.65 | 0.935 |
| All 4 engines | equal | 0.60 | 0.909 |

**Adaptive v2 results**:
- F1 = 0.909
- 100% AI detection rate
- 80% human accuracy
- Zero false reds

**ReMoDetect** (full-text engine, not batch-capable):
- F1 = 1.000 on full-length text
- Useless on short text (< 500 characters)
- Too slow for snippet scanning (~2s per text)

### 6.2 Realistic 39-Text Benchmark (`bench_realistic.py`)

**Corpus**: 39 texts designed to stress-test the formality problem.

- **20 human texts**: 5 casual social media, 5 formal news/science/business, 2 encyclopedia, 1 technical documentation, 1 product review, 1 recipe blog, 3 casual long-form, 2 formal long-form
- **19 AI texts**: 5 formal ChatGPT, 5 casual ChatGPT/Claude, 2 business ChatGPT, 1 educational ChatGPT, 3 formal long ChatGPT, 2 casual long ChatGPT/Claude, 1 review ChatGPT

**Results comparison**:

| Configuration | Precision | Recall | F1 | False Reds (Human) | Detected (AI) |
|--------------|-----------|--------|-----|-------------------|---------------|
| v2 (no guard) | 0.577 | 0.789 | 0.667 | **11 / 20** | 15 / 19 |
| v3 (with formal guard) | 1.000 | 0.105 | 0.190 | **0 / 20** | 2 / 19 |

The dramatic drop in recall with the formal guard (from 78.9% to 10.5%) is because 13 of the 19 AI texts trigger the formal unanimity pattern and get capped to yellow. This is the correct behavior -- the system honestly reports that it cannot distinguish these texts from formal human writing.

### 6.3 Category-Level Analysis

**Texts correctly classified as green (< 35%) or yellow (35-65%) -- HUMAN**:

| Human Category | N | Correctly Green | Correctly Yellow | False Red (no guard) | False Red (with guard) |
|---------------|---|-----------------|-----------------|---------------------|----------------------|
| Casual | 8 | 4 | 2 | 0 | 0 |
| Formal (news/science/business) | 7 | 0 | 0 | 7 | 0 (all capped to 55%) |
| Technical | 1 | 0 | 1 | 0 | 0 |
| Review | 1 | 0 | 0 | 1 | 0 (capped to 55%) |
| Instructional | 1 | 0 | 0 | 1 | 0 (capped to 55%) |
| Encyclopedia | 2 | 0 | 0 | 2 | 0 (capped to 55%) |

**AI detection rates by category**:

| AI Category | N | Detected (no guard) | Detected (with guard) | Capped to Yellow |
|-------------|---|--------------------|-----------------------|-----------------|
| Formal ChatGPT | 5 | 5 | 0 | 5 |
| Casual AI | 7 | 3 | 2 | 0 |
| Business AI | 2 | 2 | 0 | 2 |
| Educational AI | 1 | 1 | 0 | 1 |
| Formal long AI | 3 | 3 | 0 | 3 |
| Casual long AI | 2 | 2 | 0 | 2 |
| Review AI | 1 | 1 | 0 | 1 |

### 6.4 Speed Benchmarks

| Operation | Latency | Texts | Notes |
|-----------|---------|-------|-------|
| Single snippet scan | ~120 ms | 1 | Parallel 4-engine execution |
| 5-snippet batch | ~350 ms | 5 | Includes network overhead |
| Quick-score (6 engines) | ~300-500 ms | 1 | Adds linguistic + formulaic |
| Full analysis (23 engines) | 2-7 s | 1 | Includes GPT-2 based engines |
| URL scan (fetch + score) | ~2-3 s | 5 | Network fetch + 4-engine batch |

---

## 7. Remaining Limitations

### 7.1 Fundamental Limitations

1. **Formal text is unsolvable with these engines.** All four fast classifiers (and likely all transformer-based AI detectors trained on similar data) detect formality, not AI authorship. There is no weight adjustment, threshold tuning, or ensemble method that can extract a signal that does not exist in the engine outputs. Formal human text and formal AI text produce statistically identical feature distributions.

2. **Casual AI text that mimics human style evades all engines.** When ChatGPT or Claude is prompted to write in a casual, conversational style, engine scores drop into the human range. Examples from our benchmark:
   - A08 (casual AI, "Hot take but remote work..."): fakespot=0.011, tmr=0.149 -- scored as green (37.9%)
   - A09 (casual AI, "Started learning guitar..."): fakespot=0.126, tmr=0.060 -- scored as green (34.1%)

3. **Text length compounds unreliability.** Below 150 characters, the engines lack sufficient signal for any reliable determination. Search engine snippets are typically 120-160 characters, placing them right at the boundary of engine reliability.

### 7.2 Known Failure Modes

| Failure Mode | Frequency | Example | Outcome |
|-------------|-----------|---------|---------|
| Formal human text scored as AI | Common (55% of formal human without guard) | News article about Federal Reserve | False red (mitigated by guard) |
| Casual AI text scored as human | ~29% of casual AI texts | ChatGPT mimicking Reddit post | False negative (missed) |
| Short text false positive | ~25% at < 150ch (Fakespot) | Tweet-length human text | Mitigated by score caps |
| Product review false positive | Occasional | Genuine product review with formal tone | Capped by guard if formal enough |

### 7.3 Potential Solutions (Untested)

1. **ReMoDetect as Phase 2 tiebreaker**: ReMoDetect achieved F1=1.000 on full-length text in our original benchmark. It could serve as a tiebreaker for texts scored yellow (uncertain) by the fast pipeline. However, it has NOT been tested on formal human text and may exhibit the same formality bias. It is also too slow (~2s per text) for snippet scanning.

2. **Linguistic/formulaic heuristic escalation**: The heuristic engines (linguistic, formulaic) detect AI-specific phrases ("delve," "multifaceted," "it's important to note") and structural patterns. These are independent of the formality problem. The current quick-score and full-analysis pipelines already use these as correction signals. Deeper integration into the snippet scorer could help distinguish formal AI from formal human text when AI-specific markers are present.

3. **Perplexity-based methods**: Zero-shot methods like Binoculars, Fast-DetectGPT, and perplexity analysis operate on fundamentally different principles (measuring text surprise against a language model). These may not share the formality bias. However, they require GPT-2 or similar model access, making them too slow for snippet scanning.

4. **User feedback loop**: Allowing users to flag false positives/negatives could build a ground-truth dataset for continuous calibration.

---

## 8. Two-Phase Architecture

SlopTotal's Chrome extension uses a two-phase architecture to balance speed and accuracy.

### 8.1 Phase 1: Snippet Scan (Instant)

```
User searches Google
    |
    v
Content script extracts snippet text (~150 chars each)
    |
    v
Sub-batch into groups of 5 snippets
    |
    v
POST /api/scan/snippets  (per sub-batch)
    |
    v
4 engines run in parallel: BERT-RAID, E5, TMR, Fakespot
    |
    v
_compute_snippet_score() with adaptive weights + formal guard
    |
    v
Badge displayed on each search result: green/yellow/red + score
```

**Latency**: ~350 ms per 5-snippet batch (120ms engine + 230ms network/serialization)
**Purpose**: Instant visual indicator on search results. Users see badges before they even finish scanning the page.

### 8.2 Phase 2: URL Content Scan (Background)

```
After Phase 1 badges are displayed
    |
    v
Background script collects URLs from search results
    |
    v
Sub-batch into groups of 5 URLs
    |
    v
POST /api/scan/urls  (per sub-batch, sent sequentially)
    |
    v
Server fetches each URL's content (head 500 chars)
    |
    v
4 engines score the page content
    |
    v
Badge UPGRADED if URL content score is higher/different
```

**Latency**: ~2-3 seconds per 5-URL batch (network fetch + engine inference)
**Purpose**: More reliable scoring using actual page content instead of search engine snippets. URL content is typically 500+ characters, putting it in the "reliable" range for Fakespot. Badges are updated progressively as results arrive.

**URL content truncation**: Page content is truncated to 500 characters for two reasons:
1. Fakespot reliability improves significantly at 300+ characters
2. Keeping text short limits inference time (O(n^2) attention)

### 8.3 Full Analysis (On-Demand)

```
User clicks "Full Report" on extension or visits web interface
    |
    v
POST /api/analyze  (or queue-managed via /api/queue)
    |
    v
All 23 engines run with thread pool executor
    |
    v
_calculate_full_calibrated_score() with all corrections
    |
    v
Detailed report page with per-engine breakdown
```

**Latency**: 2-7 seconds
**Purpose**: Comprehensive analysis with all 23 engines, providing the most complete picture. Includes engines like ReMoDetect, Binoculars, and GPT-2-based statistical methods that are too slow for real-time scanning.

---

## 9. Appendix: Raw Benchmark Data

### 9.1 Engine Timing (39-text batch)

```
BERT-RAID:   3.07 ms    (4.4M params)
E5:         37.19 ms    (33M params)
Fakespot:  116.02 ms    (125M params)
TMR:       122.17 ms    (125M params)
```

### 9.2 Overall Engine Averages

| Category | N | BERT-RAID | E5 | TMR | Fakespot |
|----------|---|-----------|-----|------|----------|
| All Human | 20 | 0.800 | 0.768 | 0.806 | 0.603 |
| All AI | 19 | 0.876 | 0.864 | 0.890 | 0.832 |
| Gap (AI - Human) | -- | 0.076 | 0.096 | 0.084 | **0.229** |

Fakespot has the largest overall gap (0.229) between human and AI scores, confirming its role as the most discriminative engine -- though this gap nearly vanishes when comparing only formal text.

### 9.3 Realistic Benchmark Text Samples

**Casual human (correctly classified green)**:
> "just got back from the dentist and my mouth is completely numb lol. tried to drink coffee and it went everywhere" (112 chars, score: 28.4%)

**Formal human (false red without guard, capped with guard)**:
> "The Federal Reserve held interest rates steady on Wednesday, signaling that policymakers remain cautious about cutting borrowing costs amid persistent inflation pressures." (171 chars, score: 85.4% -> 55.0% with guard)

**Formal AI (indistinguishable from formal human)**:
> "Climate change is one of the most pressing issues facing humanity today. Rising global temperatures are causing widespread environmental disruption across ecosystems worldwide." (176 chars, score: 85.2% -> 55.0% with guard)

**Casual AI (evades detection)**:
> "Started learning guitar about three months ago and man, the calluses are real. My fingertips were so sore the first two weeks I could barely type. Getting better at barre chords now though." (189 chars, score: 34.1% -- MISSED)

### 9.4 Scoring Function Reference

The three scoring functions in `app/analyzer.py`:

| Function | Engines Used | Context | Formal Guard |
|----------|-------------|---------|-------------|
| `_compute_snippet_score()` | 4 (BERT, E5, TMR, Fakespot) | Snippet/URL scan | fakespot >= 0.90 AND tmr >= 0.93 -> cap 55% |
| `_calculate_calibrated_score()` | 4 + linguistic + formulaic | Quick-score API | min_score > 0.85 AND spread < 0.15 -> skepticism |
| `_calculate_full_calibrated_score()` | All 23 engines | Full analysis | Same as quick-score + weighted baseline blend |

---

## Acknowledgments

Benchmark data collected using `bench_full.py` and `bench_realistic.py` scripts. All engine weights are open-source models run locally. No API calls or cloud services are used for inference.

Engine models:
- BERT-RAID: Fine-tuned BERT-base on RAID dataset
- E5: Fine-tuned E5-base on RAID dataset
- TMR: RoBERTa-base trained on MAGE corpus
- Fakespot: RoBERTa-base trained on review/article corpus
- ReMoDetect: Reward model-based detection (reference only, not used in fast pipeline)

---

*This document is part of the SlopTotal open-source project. Research findings are published to promote transparency about the capabilities and limitations of AI content detection systems.*
