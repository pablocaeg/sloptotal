# Engine evaluation — 2026-07-25

Measured against the live production API (`https://api.sloptotal.com`) on a
12-thread CPU-only host. Scripts in this directory reproduce every number.

Two corpora, deliberately:

| corpus | what | size | why |
|---|---|---|---|
| `results-multidomain-20260725.json` | RAID, `attack='none'`, domains news / books / poetry / abstracts, AI from gpt4, chatgpt, llama-chat, mistral-chat | 110 (40 human, 70 AI) | modern web text — the normal case |
| `results-classics-20260725.json` | Project Gutenberg prose published 1532–1915 | 26 (all human) | a high score here is a false positive *by construction* |

The classics set exists because optimising on RAID alone produces a threshold
that mislabels literature. See "The threshold trap".

## Bugs found and fixed

### Desklib engine was a randomly-initialised network

`desklib/ai-text-detector-v1.01` ships a custom `DesklibAIDetectionModel`: a
DeBERTa-v3-large backbone under `model.*` plus a single-logit `classifier`
(1, 1024) over the mean-pooled last hidden state.

The engine loaded it with `AutoModelForSequenceClassification`, which expects the
backbone under `deberta.*` and a 2-way head. All 392 tensors mismatched;
transformers reported every one MISSING and randomly initialised the whole
network — embeddings, 24 encoder layers, pooler, head. It returned sigmoid(~0),
about 0.5 for any input, while holding 8% of the ensemble weight and being
documented as a Tier A "RAID benchmark leader".

    before   AI 0.442  human 0.444   AUC -0.003 (noise)
    after    AI 0.984  human 0.065   AUC  0.999

### Three engines were anti-correlated with ground truth

Each had *both* its direction and its threshold band wrong. DivEye's and
Readability's bands sat entirely below both observed distributions, so almost
every input clamped to 0.0 and they emitted a near-constant score.

| engine | AUC before | AUC after | what was wrong |
|---|---|---|---|
| Binoculars | 0.160 | **0.849** | CE ratio *rises* with AI; code assumed it fell |
| DivEye | 0.432 | **0.728** | surprisal CV rises with AI; band below all data |
| Readability Uniformity | 0.453 | 0.564 | Flesch CV rises with AI; band below all data |

Observed percentiles are recorded in comments at each call site.

## The threshold trap

`config.py` sets `SCORE_SUSPICIOUS = 60`, so "Likely AI-generated" requires ≥60.
Ranking is excellent (overall AUC 0.985) but the cut point discards half the
detection power:

| threshold | sensitivity | specificity | classics falsely flagged |
|---|---|---|---|
| 40 | **100%** | 92% | **13/26 (50%)** |
| 45 | 90% | 95% | 12/26 (46%) |
| 60 (current) | **47%** | 100% | 2/26 (8%) |

Per-domain false negatives at the current 60: news 16/20, poetry 8/10,
books 7/20, abstracts 6/20.

So the threshold cannot simply be lowered. At 40 SlopTotal would call half the
literary canon AI-generated — Machiavelli (1532) scores 62.5, Kafka 62.4.
**Fix the engine that causes those false positives first, then re-derive the
threshold.**

## The cause is Fakespot, not the perplexity engines

The intuitive explanation — GPT-2 has memorised the canon, so classics look
maximally predictable to the perplexity family — is **wrong**. Those engines
score classics *lower* than modern human text:

    Perplexity -0.123   Log-Rank -0.119   Cross-Perplexity -0.134   GLTR -0.161

The bias is concentrated in one engine. "Memorisation bias" below is
mean(classics) − mean(modern human): how much an engine punishes archaic prose.

| engine | classics | modern human | modern AI | bias |
|---|---|---|---|---|
| **Fakespot** | **0.645** | 0.112 | 0.995 | **+0.533** |
| SuperAnnotate | 0.596 | 0.542 | 0.414 | +0.053 |
| BERT-tiny RAID | 0.229 | 0.101 | 0.970 | +0.128 |
| ReMoDetect | 0.018 | 0.387 | 0.916 | −0.369 |
| Desklib | 0.020 | 0.107 | 0.999 | −0.088 |
| TMR | 0.058 | 0.060 | 0.987 | −0.002 |

Fakespot separates modern AI essentially perfectly (0.995 vs 0.112) but scores
pre-1920 prose at 0.645. It carries the largest single weight (0.13) *and*
anchors the "Fakespot-dominant correction" in `analyzer.py`, so its bias is
amplified rather than averaged out.

SuperAnnotate is separately miscalibrated in absolute terms on this corpus —
human 0.542 above AI 0.414 — so its weight should not be raised on the strength
of rank-based AUC alone.

### Recommended change, not yet applied

1. Cut Fakespot's weight and retire its dominant-anchor role in the calibration.
2. Redistribute toward high-AUC, low-bias engines: ReMoDetect, Desklib, TMR,
   ChatGPT Detector.
3. Re-measure **both** corpora.
4. Only then lower the verdict threshold, targeting ≥90% sensitivity with
   ≤1/26 classics flagged.

## Code detection is not supported

`use-cases/code-detection` sells AI-code detection to "engineering leads". Both
halves were tested:

- **Specificity is fine.** Six CPython stdlib modules — unambiguously human,
  written long before LLMs — scored 8.6–32.1. No false positives.
- **Sensitivity is not.** Three genuine LLM-authored Python samples scored
  26.6–51.8. **None** reached "Likely AI".

All 23 engines are natural-language detectors; `analyzer.py` already notes
"structural unreliable for code-heavy pages", and the README points to a
separate project for AI-generated code. The page should be dropped or reframed —
as written it delivers confident false reassurance, which in a code-review
context is worse than a false positive.

## Caveats

- RAID-trained engines (TMR, BERT-tiny RAID) are flattered by a RAID corpus.
  Their AUC here is optimistic.
- 26 classic chunks and 3 LLM code samples are small. Directions are clear;
  exact percentages are not precise.
- Everything was measured on `attack='none'` rows. Adversarially perturbed AI
  text is untested.
