# How the overall score is calibrated

The overall score is not an average of the engines. It comes from a small model fitted on [SlopBench](../tests/eval/slopbench/README.md), and everything that model needs is in [`app/calibration.json`](../app/calibration.json). This page explains each field in that file, what the band edges mean, and how to regenerate it.

The file is written by three fit scripts and is never edited by hand. [`app/calibration.py`](../app/calibration.py) reads it. Every number the fits report, measured on writing they never saw, is in [`tests/eval/slopbench/FINDINGS.md`](../tests/eval/slopbench/FINDINGS.md).

## The file at a glance

| Field | Written by | Used for |
|---|---|---|
| `english` | `fit.py` | the full report, for English text |
| `multilingual` | `fit_multilingual.py` | the full report, for every other language |
| `quick` | `fit_quick.py` | `/api/quick-score` and `/api/paragraph-score` |
| `version` | all three | the date of the most recent fit |
| `source` | all three | which scripts wrote the file |

`version` and `source` are labels only. A different value, `CALIBRATION_VERSION` in `calibration.py`, is a hash of `calibration.json`, `calibration.py` and `language.py`. A cached report is reused only when it was scored under the same hash, so changing any of the three files rescores old texts.

## The English section

`english` holds everything needed to turn the 23 engine scores into one number from 0 to 100. The steps are:

1. **Log-odds.** Each engine score `s` (0 to 1) becomes `logit(s) = ln(s / (1 - s))`, with `s` clamped to 0.01 to 0.99. An engine that did not report counts as 0.5, which is a logit of 0 and adds nothing.
2. **Weighted sum.** `z = intercept + sum(weight * logit(s))` over the engines.
3. **Short texts.** `z` is pulled toward a neutral value: `z = r * z + (1 - r) * length_neutral`, where `r = words / (words + length_k)`.
4. **Bands.** `z` is mapped to a 0 to 100 score by `band_knots`.

The fields:

- **`intercept`** is the log-odds when every engine says 0.5. It is 0.9571 now.
- **`weights`** gives one number per engine, all zero or above. They are fitted by logistic regression with a small L2 penalty. An engine earns weight only for what it adds once the others are known, so engines that fail together are not counted twice. Today 8 of the 23 have a weight above zero (Structural, Desklib, Fakespot, SuperAnnotate, Formulaic, Readability, Binoculars and Burstiness). The other 15 are still run and shown in the report, but they do not move the score.
- **`length_k`** controls how fast a short text is trusted. At `length_k = 5` a 20-word text keeps 80% of its log-odds (`r = 0.8`) and a 300-word text keeps 98%.
- **`length_neutral`** is the log-odds a text with almost no words is pulled toward. It is -3.6, which `band_knots` turns into a score of about 17. `length_k` and `length_neutral` are fitted together on the same texts cut to 50 and 100 words.
- **`band_knots`** is a list of `[z, score]` pairs. A score is found by interpolating in a straight line between the two knots on either side of `z`. Below the first knot the score is 0, and above the last it is 100.

Because every weight is zero or above and every step is increasing, a higher engine score can never lower the overall score. The app uses this to show the lowest and highest score still possible while engines are still reporting (`score_range` in `calibration.py`).

## What the band edges mean

The report has five verdict bands, with edges at 30, 45, 55 and 80 (`SCORE_CLEAN`, `SCORE_LOW_RISK`, `SCORE_SUSPICIOUS` and `SCORE_LIKELY_AI` in [`app/config.py`](../app/config.py)):

| Score | Verdict | Edge placed where this share of human text begins |
|---|---|---|
| up to 30 | Clean, likely human-written | 15% of human text scores above 30 |
| up to 45 | Low risk | 5% of human text scores above 45 |
| up to 55 | Suspicious | 2% of human text scores above 55 |
| up to 80 | Likely AI-generated | 0.5% of human text scores above 80 |
| above 80 | Slop detected | |

So a band is a measured false-positive rate, not an arbitrary cut. `fit.py` finds each edge by taking that share of human texts from SlopBench, with every source weighted equally so that one large source cannot decide it. The texts are scored by a model that never saw their own source (leave-one-source-out), so the edges describe writing the model has not met.

The four edges are the middle four knots in `band_knots`. The first knot is 6 below the 30 edge and the last is 4 above the 80 edge, and they pin the ends of the scale to 0 and 100. This is why the English knots look like `[-7.04, 0], [-1.04, 30], [0.29, 45], [1.16, 55], [2.20, 80], [6.20, 100]`. The `z` values are different in each section, because each model has its own scale, but the scores 0, 30, 45, 55, 80 and 100 are the same.

## The multilingual section

Text that is not English uses `multilingual`. It has the same weighted sum, with these differences:

- **One set of `weights` and one `intercept` for every language.** The English weights do not carry over: ReMoDetect is the only classifier that keeps working across scripts, and it has by far the largest weight here. 11 of the 23 engines have weight.
- **`languages`** has an entry per language with an `offset` and a `status`. The same quality of text lands in a different place on the scale in each language, so the language's offset is added to `z`. Each offset is chosen so that about 5% of that language's human text scores above 45.
- **`default_offset`** is the median of the per-language offsets. It is used for any language not listed.
- **`status`** says how far to trust a language, from 5-fold cross-validation inside that language. `supported` needs an AUC of at least 0.90 and at least 60% of AI text caught at 45. `experimental` needs an AUC of at least 0.80. Anything lower is `unsupported`. A language not listed at all is `unsupported`. The current statuses are in the README's [Scoring](../README.md#scoring) section.
- **`short_alpha` and `short_ref_words`** handle short texts. Below `short_ref_words` (150) words, `short_alpha * (1/words - 1/short_ref_words)` is subtracted from `z`. With the current `short_alpha` of 81.9 that is 1.09 at 50 words and 0.27 at 100, and nothing from 150 words up. `short_alpha` is fitted so that about 5% of short human text still lands above 45. Scripts written without spaces (Chinese, Japanese, Thai, Lao, Khmer, Burmese) skip it.
- **The score is `100 / (1 + e^-z)`.** There are no `band_knots`. The offset puts the 45 edge in the right place for each language, but the other edges are not set separately.

## The quick section

`quick` is used by `/api/quick-score` and `/api/paragraph-score`, which run only a few engines. It has the same fields as `english` and the same method. It is fitted on only the six engines the quick path runs, four of which have weight now. Its `band_knots` put the same 30, 45, 55 and 80 edges at the same shares of human text. The quick and paragraph scans report clean, mixed or AI from two edges, `QUICK_CLEAN_MAX` (35) and `QUICK_AI_MIN` (65), in `config.py`.

## What is not in the file

The confidence label is set in `calibration.py`, not in the JSON:

- **Low** under 80 words, for an unsupported language, or when the score is between 35 and 65.
- **Medium** for an experimental language, or when the score is between 15 and 80.
- **High** otherwise.

Words are counted by `count_words` in `app/language.py`, which counts Chinese, Japanese, Thai, Lao, Khmer and Burmese by characters.

## A worked example

Every engine reports the same score `s`, for an English text with `words` words. These values were computed with the `calibration.json` dated 2026-10-10:

| All engines say | 20 words | 300 words |
|---|---|---|
| 0.1 | 22.2 | 23.3 |
| 0.5 | 42.3 | 51.8 |
| 0.9 | 82.5 | 89.7 |

Short texts are pulled toward a low score (about 17 for English), so in every row the 20-word text scores lower than the 300-word one. A short text needs stronger evidence before it is called AI. These values change whenever the file is refitted.

## Regenerating the file

The fit scripts need `numpy`, `scipy` and `scikit-learn`, which are only used offline and are not in `requirements-dev.txt`. Run them from `tests/eval/slopbench`. The three fits are independent, so you can refit one section without the others:

```bash
pip install numpy scipy scikit-learn
cd tests/eval/slopbench
python fit.py results-20260930.jsonl results-short-20261001.jsonl results-short-ai-20261001.jsonl > report.md
python fit_multilingual.py ../multilingual/results-20260930.jsonl ../multilingual/results-short-20261005.jsonl > report-multilingual.md
python fit_quick.py results-20260930.jsonl results-short-20261001.jsonl results-short-ai-20261001.jsonl > quick-report.md
```

Each command replaces only its own section of `app/calibration.json` and sets `version` to today's date. Each also prints a report, which the commands above save to a file, and `FINDINGS.md` quotes those reports. The `.jsonl` files are the committed SlopBench scores. To score new texts, see "Reproducing it" in the [SlopBench README](../tests/eval/slopbench/README.md).

Run on the committed files, these three commands reproduce all three sections exactly. Only the `version` date changes.

If you change an engine, a weight or the calibration, re-run the corpora and report the before and after numbers in the pull request, as [AGENTS.md](../AGENTS.md) asks.
