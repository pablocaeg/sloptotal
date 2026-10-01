# SlopBench findings, October 2026

What SlopBench measured about SlopTotal and its 23 engines, and how the
calibration that followed was chosen. The corpus is described in
[README.md](README.md); every number here is reproduced by `analyze.py`,
`fit.py` and `fit_multilingual.py` from the committed results.

## The ensemble before calibration

1,626 human texts written before ChatGPT and 1,626 AI counterparts, scored by
the production ensemble as of 2026-10-01:

| AUC | AI caught at 1% FPR | AI caught at 5% FPR | AI flagged (>45) | Human flagged (>45) | Human called AI (≥55) |
|---|---|---|---|---|---|
| 0.905 | 31.6% | 58.5% | 84.1% | 14.1% | 7.7% |

The README and the site quoted AUC 0.974 from 110 RAID samples. That number
was real for RAID's 2023 models and four domains; on current models across
15 kinds of writing it is 0.905, and the honest headline is the false-positive
rate: one human text in thirteen was called "Likely AI".

## Who gets wrongly flagged

Human text scoring above 45, by source:

| Human text | Flagged (>45) | Called AI (≥55) |
|---|---|---|
| CC-News articles, 2016-2019 | 64.4% | 44.4% |
| BBC articles, 2010-2017 | 43.3% | 20.0% |
| College admission essays | 34.3% | 12.9% |
| TOEFL essays by non-native writers | 34.1% | 22.0% |
| Wikinews articles, 2020-2022 | 20.0% | 7.8% |
| Wikipedia, as of 2019 | 16.7% | 8.7% |
| arXiv abstracts | 10.0% | 6.0% |
| Stack Exchange answers | 8.0% | 3.3% |
| ELI5 answers | 6.7% | 4.0% |
| Amazon reviews | 3.3% | 1.3% |
| Reddit comments, WritingPrompts stories | 1.3% | 0-1.3% |
| US 8th-grade essays | 1.1% | 0.0% |
| Literature, 1532-1915 | 0.0% | 0.0% |

Three findings:

- **Memorisation, not news prose, explains most of the news problem.** The
  same register written after GPT-2's training data was collected (Wikinews,
  2020-2022) is flagged a third as often as 2016-2019 news (20% against 64%).
  SuperAnnotate's mean on human news falls from 0.53 to 0.16 and Binoculars'
  from 0.50 to 0.19: they were reacting to text they had effectively seen.
  What remains is the TMR classifier, which scores human news 0.98 whatever
  the year.
- **Non-native writers are flagged far more than native ones.** The TOEFL
  essays of Liang et al. (2023) are flagged 34% of the time against 1% for US
  8th graders. Liang et al. report seven commercial detectors misclassifying
  61% of the same essays; SlopTotal is better, and still not fair.
- **The pre-1920 literature control set stays clean** (0 of 87), so the
  old-prose bias fixed in July is still fixed.

## Short texts

The same 301 human texts, cut down:

| Length | Median score | Flagged (>45) | Called AI (≥55) |
|---|---|---|---|
| Full | 20.2 | 18.3% | 10.0% |
| 100 words | 25.6 | 22.6% | 11.6% |
| 50 words | 34.0 | 27.2% | 15.6% |

At 50 words, two thirds of TOEFL essays and CC-News articles and half of
college essays and Wikinews articles are flagged.

## Which models are hard to catch

| Model | Texts | AUC vs all human text | Flagged (>45) |
|---|---|---|---|
| `mistralai/mistral-small-2603` | 235 | 0.956 | 93.6% |
| `meta-llama/llama-4-maverick` | 247 | 0.947 | 93.1% |
| `qwen/qwen3.8-flash` | 256 | 0.938 | 89.8% |
| `openai/gpt-6-luna` | 264 | 0.933 | 86.7% |
| `deepseek/deepseek-v4.1-flash` | 272 | 0.873 | 79.4% |
| `z-ai/glm-5.3-flash` | 253 | 0.806 | 64.4% |

Free-tier models with fewer samples: Gemma 4 31B 0.972 (16 texts), Qwen 3.8
27B 0.853 (21), Nemotron 3 Super 0.832 (24), Nemotron 3 Ultra 0.818 (26).

## Rewritten AI text

| Variant | Texts | Flagged (>45) | Called AI (≥55) | Median | Median before rewriting |
|---|---|---|---|---|---|
| AI, paraphrased by a second model | 267 | 89.5% | 72.3% | 64.1 | 68.6 |
| AI, "humanized" | 269 | 75.8% | 52.8% | 56.2 | 68.3 |
| Human, polished by a model | 257 | 59.9% | 41.6% | 50.1 | 22.0 |
| Human opening, continued by a model | 251 | 61.0% | 43.0% | 51.1 | 22.2 |

Paraphrasing barely helps; a "humanizer" prompt costs about one AI text in
five its "Likely AI" verdict. Human text that a model polished moves from a
median of 22 to 50, squarely into the band the report calls Suspicious, which
is where a mixed text belongs.

## The engines on their own

AUC of each engine, AI against human text, with its July RAID figure:

| Engine | SlopBench | RAID (July) |
|---|---|---|
| SuperAnnotate | 0.938 | 1.000 |
| Desklib DeBERTa | 0.936 | 1.000 |
| Fakespot | 0.917 | 0.999 |
| ReMoDetect | 0.865 | 0.941 |
| Structural Analysis | 0.755 | |
| TMR Detector | 0.749 | 1.000 |
| E5-Small | 0.721 | 0.999 |
| ChatGPT Detector | 0.688 | |
| Binoculars | 0.680 | 0.849 |
| BERT-tiny RAID | 0.654 | |
| Perplexity, Log-Rank | 0.644 | 0.901, 0.909 |
| Fast-DetectGPT | 0.633 | |
| GLTR | 0.622 | 0.904 |
| Cross-Perplexity | 0.618 | |

The classifiers that topped RAID largely do not carry over to current models:
TMR gives modern human text a mean of 0.72, and the GPT-2 statistical tests,
which were among the most dependable engines on RAID, are close to a coin flip
on text from 2026 models. Four classifiers (SuperAnnotate, Desklib, Fakespot,
ReMoDetect) do the real work. Per-engine pages on sloptotal.com carry these
numbers.
