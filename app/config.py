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
# Weights based on MAGE + RAID empirical evaluation:
#   Fakespot: best discriminator (human/AI gap=32%)
#   E5/BERT-RAID: good but over-trigger on formal text (gap=7-10%)
#   TMR: almost no discrimination (gap=1%)
#   Linguistic/Formulaic: independent signal, catches AI phrases ML models miss
ENGINE_WEIGHTS = {
    # Tier A — Highest accuracy engines
    "burstiness": 0.09,
    "classifier_remodetect": 0.08,
    "classifier_fakespot": 0.13,  # Best discriminator, gap=32%
    "classifier_desklib": 0.08,  # DeBERTa-v3, trained on GPT-4/Claude
    "classifier_openai": 0.06,
    "linguistic": 0.08,  # Independent AI phrase signal
    "formulaic": 0.07,  # Independent structural signal
    # Tier B — Good accuracy
    "classifier_superannotate": 0.06,  # RoBERTa-large, low FPR optimized
    "fast_detectgpt": 0.04,
    "cross_perplexity": 0.04,
    "classifier_e5": 0.05,
    "classifier_bert_raid": 0.04,
    "gltr": 0.03,
    # Tier C — Moderate accuracy, some false positives
    "classifier_tmr": 0.02,  # Gap=1%, almost useless
    "classifier_chatgpt": 0.03,
    "perplexity": 0.02,
    "log_rank": 0.02,
    # Tier D — Low accuracy, kept for breadth
    "binoculars": 0.02,
    "diveye": 0.01,
    "structural": 0.01,
    "vocabulary": 0.01,
    "readability": 0.005,
    "sentiment": 0.005,
}

# Minimum text length for analysis
MIN_TEXT_LENGTH = 50
