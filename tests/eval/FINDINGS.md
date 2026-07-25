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

## Applied: unanimous-high skepticism was destroying sensitivity

Separately from the weights, the largest single cause of missed detections was
Step 4 of `_calculate_full_calibrated_score`. It existed to stop formal human
prose being confidently misread as AI. Measured, it did the reverse — it fired on
**69 of 70** RAID AI samples and **0 of 66** human samples (40 RAID human + 26
literary). Four classifiers agreeing above 0.85 is not a false-positive symptom;
on this evidence it is the ensemble being right. Pulling those scores toward 0.45
compressed all AI output into roughly 45–59.

It now additionally requires human writing markers in the text itself
(contractions, first-person, slang) via `_human_signal_score`. The stacked
"no markers" penalty was also softened from 0.35 to 0.15.

Re-measured on both full corpora (110 and 26, no partial runs):

| | AI mean | human mean | classics mean | sens @60 | spec @60 | classics ≥60 |
|---|---|---|---|---|---|---|
| before | 58.2 | 10.7 | 38.1 | 47% | 100% | 2/26 |
| after | **67.5** | 10.7 | 38.2 | **61%** | 100% | 3/26 |

Sensitivity at other cut points: @65 36%→51%, @70 16%→43%. Human and classics
means are unchanged, as predicted — those samples never reached the branch, so
gating it could not move them.

**Threshold left at 60 deliberately.** The remaining options are all bad until
Fakespot is dealt with: 55 gives 63% sensitivity but flags 8/26 classics, and 65
gives 0 classics but only 51% sensitivity. Fixing Fakespot's literary bias is
what unblocks lowering the threshold, so do that first, in the order above.

Raw results: `results-*-20260725.json` (before) and
`results-*-20260725-postcalibration.json` (after).

### Measurement hazard

Pushing to `master` auto-deploys and restarts the API container, which returns
502s from nginx mid-run. An early version of the runner had no retries and
silently completed with 23 of 110 rows, producing a plausible but wrong mean.
`run_any.py` retries and exits non-zero on an incomplete run — use it, and do not
push while measuring.

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

## Applied: Fakespot demoted, weights re-derived, thresholds set from data

Three changes measured together (v3), on the same full corpora:

1. **SuperAnnotate was a second randomly-initialised head.** Its trained head is
   named `dense` at top level; `RobertaForSequenceClassification` looks for
   `classifier.*`, so the real head was discarded and a random one used. It
   measured **AUC 0.037** across the multidomain corpus — almost perfectly
   inverted — while holding 6% weight as the "low false-positive rate" engine.
   The abstracts-only corpus had reported 1.000 for it, which is how it hid: a
   random projection can rank one narrow domain well by luck. Loaded correctly:
   AI slop 0.9995, Austen 0.0009, Melville 0.0029.
2. **Fakespot is no longer the anchor**, in either the full or quick path, and
   its weight drops 0.13 → 0.033.
3. **All weights re-derived** from Somers' D scaled by (1 − literary bias).

| | AI mean | human mean | AUC | classics mean | classics max |
|---|---|---|---|---|---|
| v1 original | 58.2 | 10.7 | 0.985 | 38.1 | 62.5 |
| v2 skepticism gated | 67.5 | 10.7 | 0.987 | 38.2 | 62.3 |
| **v3 this change** | 67.8 | 20.2 | 0.974 | **10.2** | **24.5** |

**The literary false positives are gone.** 0 of 26 classics are flagged at *any*
threshold, against 13 of 26 at threshold 40 before. Machiavelli went 62.5 → below
25. The cost is a modest rise in modern-human mean (10.7 → 20.2) and 0.013 of
AUC; worth it, because the failure it removes was the product's worst
credibility problem.

### Thresholds, finally movable

Distributions (n = 70 AI / 40 modern human / 26 literary):

| | p50 | p75 | p90 | p95 | max |
|---|---|---|---|---|---|
| modern human | 19.7 | 25.5 | 36.6 | 49.2 | 59.9 |
| literary 1532-1915 | 9.8 | 13.0 | 16.0 | 18.8 | 24.5 |
| AI | 65.8 | 85.2 | 90.8 | 91.7 | 96.6 |

Bands moved from 20/40/60/80 to **30/45/55/80**. Youden's J peaks at 40 (100%
sensitivity, 94% specificity), but the "Likely AI" line sits above it on purpose:
a false accusation costs a student or job applicant much more than a missed
detection costs the checker. The Suspicious band carries the difference — it
alerts without asserting.

Resulting behaviour:

| | Clean | Low risk | Suspicious | Likely AI | Slop |
|---|---|---|---|---|---|
| AI (70) | 0 | 7 | 19 | 16 | 28 |
| modern human (40) | 33 | 4 | 2 | 1 | 0 |
| literary human (26) | **26** | 0 | 0 | 0 | 0 |

90% of AI reaches Suspicious or above; 63% reaches Likely AI or worse; 2% of
human text (1 of 66) is wrongly called Likely AI; every literary sample reads
Clean.

`config.SCORE_*` were dead constants — `score_to_verdict_str()` in schemas.py
carried its own hardcoded copy. schemas.py now reads config, so there is one
source of truth.

### Still open

- Sensitivity at the Likely-AI line is 63%. Raising it further means either
  accepting more false accusations or finding signal the current 23 engines do
  not have.
- TMR and BERT-tiny RAID remain RAID-trained and evaluated on RAID; their
  contribution is damped 0.65× but a non-RAID corpus would measure them honestly.
- Adversarially perturbed AI text (`attack != 'none'`) is still untested.
