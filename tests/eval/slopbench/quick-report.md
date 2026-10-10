# Quick path calibration on SlopBench

1626 human and 2162 AI texts, leave-one-source-out.

| | AUC | AI flagged (>45) | AI called AI (≥55) | Human flagged (>45) | Human called AI (≥55) |
|---|---|---|---|---|---|
| Quick, fitted (held out) | 0.896 | 62.9% | 38.1% | 4.9% | 2.1% |

At the quick verdict edges (clean ≤35, ai >65): human called ai 1.4%, human clean 90.7%, AI called ai 31.5%.

## Human texts by source (flagged >45 / called AI ≥55)

| Source | n | >45 | ≥55 |
|---|---|---|---|
| academic-arxiv | 150 | 1.3% | 0.7% |
| classics-gutenberg | 87 | 3.4% | 1.1% |
| creative-writingprompts | 150 | 4.0% | 1.3% |
| encyclopedia-wikipedia | 150 | 15.3% | 10.7% |
| essay-college | 70 | 4.3% | 2.9% |
| essay-hewlett | 88 | 0.0% | 0.0% |
| essay-toefl | 91 | 25.3% | 7.7% |
| explanation-eli5 | 150 | 2.0% | 0.0% |
| news-bbc | 60 | 0.0% | 0.0% |
| news-ccnews | 90 | 0.0% | 0.0% |
| news-wikinews | 90 | 8.9% | 3.3% |
| qa-stackexchange | 150 | 3.3% | 1.3% |
| review-amazon | 150 | 2.0% | 0.0% |
| social-reddit | 150 | 0.7% | 0.0% |

Short texts: k = 30, neutral = -1.90

| Engine | Weight |
|---|---|
| Fakespot | 0.570 |
| Linguistic Markers | 0.115 |
| Formulaic Patterns | 0.113 |
| TMR Detector | 0.022 |
| BERT-tiny RAID | 0.000 |
| E5-Small | 0.000 |
