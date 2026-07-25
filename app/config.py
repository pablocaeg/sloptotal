import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
STATIC_DIR = PROJECT_ROOT / "web" / "static"

# Database settings (configurable via environment)
DATA_DIR = Path(os.getenv("SLOPTOTAL_DATA_DIR", str(BASE_DIR.parent / "data")))
DATABASE_PATH = DATA_DIR / os.getenv("SLOPTOTAL_DB_NAME", "sloptotal.db")
CACHE_ENABLED = os.getenv("SLOPTOTAL_CACHE_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Database connection settings
DB_TIMEOUT = float(os.getenv("SLOPTOTAL_DB_TIMEOUT", "30.0"))  # seconds
DB_BUSY_TIMEOUT = int(os.getenv("SLOPTOTAL_DB_BUSY_TIMEOUT", "5000"))  # milliseconds

# GPT-2 model name for perplexity engines
GPT2_MODEL = "gpt2-medium"

# Scoring thresholds
SCORE_CLEAN = 20
SCORE_LOW_RISK = 40
SCORE_SUSPICIOUS = 60
SCORE_LIKELY_AI = 80

# Engine weights for overall score (must sum to 1.0)
#
# Derived from measurement, not judgement — see tests/eval/FINDINGS.md.
# Corpora: 110 RAID samples across news/books/poetry/abstracts (70 AI from
# gpt4/chatgpt/llama-chat/mistral-chat, 40 human) plus 26 Project Gutenberg
# chunks published 1532-1915, where any high score is a false positive by
# construction. Measured 2026-07-25.
#
# weight is proportional to Somers' D (2*AUC - 1), multiplied by
# (1 - literary_bias) where literary_bias is mean(classics) - mean(modern
# human). TMR and BERT-tiny RAID are additionally damped 0.65x because they are
# RAID-trained and the corpus is RAID, so their AUC is optimistic.
#
# What changed, and why the old table was wrong:
#
#   fakespot     0.13 -> 0.033  AUC 0.999 but literary bias +0.533: it scored
#                               pre-1920 prose 0.645 vs 0.112 for modern human
#                               text. It also anchored the whole calibration, so
#                               that bias was amplified rather than averaged
#                               out. It is now one voice among many.
#   burstiness   0.09 -> 0.011  AUC 0.578, yet was joint-largest weight.
#   linguistic   0.08 -> 0.030  AUC 0.713.
#   log_rank     0.02 -> 0.059  AUC 0.909, zero literary bias.
#   gltr         0.03 -> 0.058  AUC 0.904, zero literary bias.
#   perplexity   0.02 -> 0.058  AUC 0.901, zero literary bias.
#
# The GPT-2 perplexity family was assumed to be what flags classics, the
# intuition being that GPT-2 has memorised the canon so it reads as maximally
# predictable. The data says the opposite: those engines score classics *lower*
# than modern human text and are among the most dependable in the ensemble.
#
# superannotate is weighted top tier on its post-fix measurement (near-perfect
# separation, no literary bias). Before its loading bug was fixed it measured
# AUC 0.037 — inverted — while carrying 6% of the weight.
ENGINE_WEIGHTS = {
    # Neural classifiers — strongest separation, no bias against archaic prose
    "classifier_desklib": 0.0725,
    "classifier_e5": 0.0722,
    "classifier_superannotate": 0.0699,
    "classifier_remodetect": 0.0639,
    "classifier_chatgpt": 0.0476,
    "classifier_tmr": 0.0470,  # damped: RAID-trained, RAID corpus
    "classifier_bert_raid": 0.0410,  # damped: RAID-trained, RAID corpus
    "classifier_openai": 0.0392,
    "classifier_fakespot": 0.0326,  # capable, but biased against literary prose
    # Statistical — consistently strong and, notably, no literary bias
    "log_rank": 0.0592,
    "gltr": 0.0584,
    "perplexity": 0.0581,
    "cross_perplexity": 0.0566,
    "fast_detectgpt": 0.0557,
    "binoculars": 0.0486,
    "diveye": 0.0332,
    # Linguistic heuristics — weak alone, kept for independent signal
    "structural": 0.0486,
    "linguistic": 0.0303,
    "formulaic": 0.0283,
    "vocabulary": 0.0117,
    "readability": 0.0117,
    "burstiness": 0.0105,
    "sentiment": 0.0032,
}

# Minimum text length for analysis
MIN_TEXT_LENGTH = 50
