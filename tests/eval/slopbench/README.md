# SlopBench

An English benchmark for AI text detectors, built so that its numbers mean
something outside the lab: every human text provably predates ChatGPT, every
AI text has a human counterpart on the same topic and at the same length, and
the hard cases people actually argue about are kept apart from the rest.

| Part | Texts | What |
|---|---|---|
| Human | 1,626 | 15 sources, all written before November 2022 |
| AI | 1,626 | One counterpart per human text, from 14 models |
| Hard cases | 1,044 | Paraphrased AI, "humanized" AI, human text polished by AI, human text continued by AI |
| Grey zone | 91 | TOEFL essays polished by GPT-4 (Liang et al. 2023) |

Results and the calibration they drove are in [FINDINGS.md](FINDINGS.md).

## Human text

| Source | Texts | Mean words | Written | Where from |
|---|---|---|---|---|
| `news-ccnews` | 90 | 403 | 2016-2019 | CC-News (Common Crawl) |
| `news-bbc` | 60 | 394 | 2010-2017 | BBC articles in XSum |
| `news-wikinews` | 90 | 347 | Mar 2020 - Oct 2022 | Wikinews, revision as of 2022-10-31 |
| `encyclopedia-wikipedia` | 150 | 367 | before 2019 | Wikipedia, revision as of 2019-01-01 |
| `academic-arxiv` | 150 | 181 | 2010-2021 | arXiv abstracts |
| `qa-stackexchange` | 150 | 329 | 2014-2021 | Top answers on 25 non-technical Stack Exchange sites |
| `explanation-eli5` | 150 | 143 | 2012-2019 | r/explainlikeimfive answers |
| `social-reddit` | 150 | 256 | 2006-2016 | Reddit comments (Webis-TLDR-17) |
| `creative-writingprompts` | 150 | 446 | 2017-2018 | r/WritingPrompts stories |
| `review-amazon` | 150 | 111 | 1995-2013 | Amazon product reviews |
| `essay-toefl` | 91 | 107 | before 2022 | TOEFL essays by non-native writers (Liang et al. 2023) |
| `essay-hewlett` | 88 | 378 | 2012 | US 8th-grade essays (Hewlett ASAP, via Liang et al.) |
| `essay-college` | 70 | 612 | before 2022 | US college admission essays (via Liang et al.) |
| `classics-gutenberg` | 87 | 309 | 1532-1915 | 29 works on Project Gutenberg, three passages each |

Two kinds of human text are there on purpose. Old web news (`news-ccnews`,
`news-bbc`) and Wikipedia are the kind of text detectors and language models
were trained on, so they show what a detector does with text it has
effectively memorised; `news-wikinews` is the same register written after
GPT-2's training data was collected, which separates memorisation from a bias
against news prose. The essays and the classics are fairness checks: a high
score on a non-native writer's essay or on Machiavelli is an error a person
pays for.

Data quality rules, all in `build_human.py`:

- Stack Exchange answers come from the official API, not a dump: the popular
  Hugging Face export pairs answers with the wrong questions. Only answers
  written **and last edited** before 2022 are used, so no later rewrite with an
  AI tool can slip in.
- Wikipedia and Wikinews text is the revision as of a fixed date, not today's.
- Paragraph breaks are kept; several engines read document structure.
- Sexually explicit text and slurs are filtered out, and texts are capped at
  600 words on a sentence boundary.

## AI text

Each human sample keeps its `seed`: the headline, question, prompt, title or
subject it was written for. Its counterpart is asked for with that seed, in
the same register and at about the same word count, with the request a person
would actually type ("Write a news article with the headline ..."). No prompt
asks the model to evade detection. The essay sets come without their prompts,
so a model was first asked which question each essay answers.

| Model | Texts | Note |
|---|---|---|
| `deepseek/deepseek-v4.1-flash` | 272 | |
| `openai/gpt-6-luna` | 264 | |
| `qwen/qwen3.8-flash` | 256 | |
| `z-ai/glm-5.3-flash` | 253 | |
| `meta-llama/llama-4-maverick` | 247 | |
| `mistralai/mistral-small-2603` | 235 | |
| `nvidia/nemotron-3-ultra-550b-a55b` | 26 | free tier |
| `nvidia/nemotron-3-super-120b-a12b` | 24 | free tier |
| `qwen/qwen3.8-27b` | 21 | free tier |
| `google/gemma-4-31b-it` | 16 | free tier |
| `x-ai/grok-4.3`, `anthropic/claude-haiku-4.5`, `openai/gpt-6.1-sol`, `moonshotai/kimi-k2.6` | 12 | first test run only |

Models are assigned by a stable hash of the sample id, so every model covers
every domain. Reasoning is switched off (or kept low and out of the reply for
models that cannot switch it off). Replies where a reasoning model narrated
the request instead of answering it are rejected; two that slipped through
were removed. Every row records its model, prompt, temperature and date.

The set leans on cheap and open-weight models, which is what most machine
text on the web comes from; frontier models are thinly represented, and no
Anthropic model beyond three test samples.

## Hard cases

Built by `make_hard.py` from a fixed sample of 20 texts per source, each
rewritten by a different model from the one that wrote it:

| Variant | Label | What |
|---|---|---|
| `ai-paraphrased` | AI | AI text reworded by a second model |
| `ai-humanized` | AI | AI text rewritten the way "humanizer" tools promise |
| `human-ai-polished` | grey | Human text with clarity and flow improved by a model |
| `mixed-continued` | grey | A human opening continued by a model in the same voice |

## Reproducing it

```bash
python build_human.py                                  # human side (no key)
OPENROUTER_API_KEY=... python generate_ai.py           # AI side
OPENROUTER_API_KEY=... python make_hard.py             # hard cases
SLOPTOTAL_URL=http://127.0.0.1:8000 python score.py results.jsonl
python analyze.py results.jsonl                        # tables
python fit.py results.jsonl results-short.jsonl        # calibration
```

Generating the AI side, the hard cases and the extra multilingual AI text cost $1.73 through OpenRouter.

## Licences

Each row's `license` and `ref` fields say where it came from. Wikipedia
(CC BY-SA 3.0), Wikinews (CC BY 2.5) and Stack Exchange (CC BY-SA 4.0) text is
attributed by revision or answer link, and the Stack Exchange author is named.
The Liang et al. essays are MIT-licensed; Project Gutenberg texts are public
domain; arXiv metadata is CC0. CC-News, XSum, Webis-TLDR-17, ELI5,
WritingPrompts and the Amazon reviews are research datasets used here for
evaluation, under their own terms.
