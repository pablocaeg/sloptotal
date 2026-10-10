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

# Verdict band boundaries, set from the measured score distributions rather than
# round numbers. See tests/eval/FINDINGS.md (2026-07-25).
#
# These constants were previously dead: score_to_verdict_str() in schemas.py had
# its own hardcoded copy (20/40/60/80) and nothing imported these. schemas.py now
# reads them, so there is one source of truth.
#
# Observed distributions after the reweighting, n=70 AI / 40 modern human /
# 26 literary human:
#
#                        p50    p75    p90    p95    max
#   modern human        19.7   25.5   36.6   49.2   59.9
#   literary 1532-1915   9.8   13.0   16.0   18.8   24.5
#   AI                  65.8   85.2   90.8   91.7   96.6
#
# Chosen so that:
#   - 90% of human text (both corpora) reads Clean:      < 30
#   - 90% of AI text reaches Suspicious or above:       >= 45
#   - "Likely AI-generated" is reserved for high confidence: >= 55
#     which measures 63% sensitivity at 98% specificity, with 0 of 26 literary
#     samples flagged at any threshold.
#
# Youden's J peaks at 40 (100% sensitivity, 94% specificity), but a false
# accusation costs a student or job applicant far more than a missed detection
# costs the checker, so the "Likely AI" line sits deliberately above the
# J-optimal point. The Suspicious band carries the difference: it alerts without
# asserting.
SCORE_CLEAN = 30
SCORE_LOW_RISK = 45
SCORE_SUSPICIOUS = 55
SCORE_LIKELY_AI = 80

# The quick scan and the paragraph scan report clean / mixed / ai rather than the
# five report bands, because the Chrome extension shows three states. These are
# their edges, kept here so they cannot drift from the bands above without a test
# noticing. A paragraph is counted as AI only when it is strictly above QUICK_AI_MIN,
# matching the previous `p["score"] > 65` in paragraph_analyze.
QUICK_CLEAN_MAX = 35
QUICK_AI_MIN = 65

# Minimum text length for analysis
MIN_TEXT_LENGTH = 50

# Longer submissions are accepted and cut at a word boundary. The classifiers
# already sample at most MAX_WINDOWS windows, so text beyond this adds cost
# without changing the classifier scores.
MAX_ANALYSED_CHARS = 100_000
