import logging
import os
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from app.schemas import (
    AnalysisReport,
    EngineResult,
    score_to_verdict_str,
    score_to_engine_verdict,
)
from app.config import ENGINE_WEIGHTS, CACHE_ENABLED
from app.cache import compute_text_hash
from app.database import (
    create_report,
    get_report as db_get_report,
    get_report_by_hash,
    get_pending_report_by_hash,
    get_recent_reports as db_get_recent_reports,
    mark_report_complete,
    insert_engine_result_sync,
    update_report_score_sync,
    cleanup_connections,
    log_scan_sync,
)
from app.engines.perplexity import PerplexityEngine
from app.engines.burstiness import BurstinessEngine
from app.engines.linguistic import LinguisticEngine
from app.engines.structural import StructuralEngine
from app.engines.vocabulary import VocabularyEngine
from app.engines.formulaic import FormulaicEngine
from app.engines.readability import ReadabilityEngine
from app.engines.sentiment import SentimentEngine
from app.engines.classifier_openai import ClassifierOpenAIEngine
from app.engines.classifier_chatgpt import ClassifierChatGPTEngine
from app.engines.cross_perplexity import CrossPerplexityEngine
from app.engines.classifier_remodetect import ClassifierReMoDetectEngine
from app.engines.classifier_fakespot import ClassifierFakespotEngine
from app.engines.classifier_e5 import ClassifierE5Engine
from app.engines.gltr import GLTREngine
from app.engines.log_rank import LogRankEngine
from app.engines.diveye import DivEyeEngine
from app.engines.fast_detectgpt import FastDetectGPTEngine
from app.engines.binoculars import BinocularsEngine
from app.engines.classifier_tmr import ClassifierTMREngine
from app.engines.classifier_bert_raid import ClassifierBERTRaidEngine
from app.engines.classifier_desklib import ClassifierDesklibEngine
from app.engines.classifier_superannotate import ClassifierSuperAnnotateEngine

log = logging.getLogger("sloptotal.analyzer")

# Pending analyses: report_id -> asyncio.Queue of (key, EngineResult) tuples
_pending: dict[str, asyncio.Queue] = {}

# Track received results count per report for score calculation
_result_counts: dict[str, int] = {}

# Lock for pending dict modifications
_pending_lock = asyncio.Lock()

# --- Shared engine instances (deduplicated across snippet/quick/full lists) ---
_bert_raid_engine = ClassifierBERTRaidEngine()
_e5_engine = ClassifierE5Engine()
_fakespot_engine = ClassifierFakespotEngine()
_tmr_engine = ClassifierTMREngine()
_linguistic_engine = LinguisticEngine()
_formulaic_engine = FormulaicEngine()
_structural_engine = StructuralEngine()
_vocabulary_engine = VocabularyEngine()
_readability_engine = ReadabilityEngine()
_sentiment_engine = SentimentEngine()

# Snippet engines - Fakespot only (sole ML engine with genuine discriminative power)
# BERT/E5/TMR removed: they detect formality, not AI authorship (gap <10%)
# Fakespot has AI-vs-human gap of 0.229 — the only reliable signal
_snippet_engines = [
    ("classifier_fakespot", _fakespot_engine),  # 125M params, ~113ms (AI gap=0.229)
]

# Quick engines - ML classifiers + fast heuristic engines for scoring
_quick_engines = [
    ("classifier_bert_raid", _bert_raid_engine),  # 4.4M params, ultra-fast
    ("classifier_e5", _e5_engine),  # 33M params, RAID #2
    ("classifier_tmr", _tmr_engine),  # 125M params, 97.3% accuracy
    ("classifier_fakespot", _fakespot_engine),  # 125M params, high signal
    ("linguistic", _linguistic_engine),  # Pure regex, <1ms — AI phrase detection
    ("formulaic", _formulaic_engine),  # Pure regex, <1ms — structural patterns
]

# Quick engine weights (normalized)
_quick_weights = {
    "classifier_bert_raid": 0.15,  # Fast but less accurate
    "classifier_e5": 0.25,  # Good balance
    "classifier_tmr": 0.35,  # Best accuracy
    "classifier_fakespot": 0.25,  # High signal
}

_engines = [
    # Tier A — High-accuracy RAID-trained classifiers
    ("classifier_tmr", _tmr_engine),
    ("classifier_remodetect", ClassifierReMoDetectEngine()),
    # Tier B — Zero-shot / model-based methods
    ("binoculars", BinocularsEngine()),
    ("fast_detectgpt", FastDetectGPTEngine()),
    ("perplexity", PerplexityEngine()),
    ("cross_perplexity", CrossPerplexityEngine()),
    # Tier C — Other classifiers
    ("classifier_fakespot", _fakespot_engine),
    ("classifier_e5", _e5_engine),
    ("classifier_bert_raid", _bert_raid_engine),
    ("classifier_openai", ClassifierOpenAIEngine()),
    ("classifier_chatgpt", ClassifierChatGPTEngine()),
    (
        "classifier_desklib",
        ClassifierDesklibEngine(),
    ),  # DeBERTa-v3, trained on GPT-4/Claude
    (
        "classifier_superannotate",
        ClassifierSuperAnnotateEngine(),
    ),  # RoBERTa-large, low FPR
    # Tier D — GPT-2 derived statistics
    ("gltr", GLTREngine()),
    ("log_rank", LogRankEngine()),
    ("diveye", DivEyeEngine()),
    ("burstiness", BurstinessEngine()),
    # Tier E — Heuristic engines
    ("linguistic", _linguistic_engine),
    ("structural", _structural_engine),
    ("vocabulary", _vocabulary_engine),
    ("formulaic", _formulaic_engine),
    ("readability", _readability_engine),
    ("sentiment", _sentiment_engine),
]

# --- CPU-aware executor splitting (Phase 2) ---
_cpu_count = os.cpu_count() or 6
_reserved = int(os.getenv("SLOPTOTAL_RESERVED_CORES", "2"))
_usable = max(_cpu_count - _reserved, 2)

_snippet_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("SLOPTOTAL_SNIPPET_WORKERS", str(min(6, _usable)))),
    thread_name_prefix="snippet",
)
_full_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("SLOPTOTAL_FULL_WORKERS", str(_usable))),
    thread_name_prefix="full",
)

# --- HTTP-level concurrency guards (Phase 4) ---
_max_full = int(os.getenv("SLOPTOTAL_MAX_CONCURRENT_FULL", "2"))
_max_snippet = int(os.getenv("SLOPTOTAL_MAX_CONCURRENT_SNIPPET", "4"))
_full_semaphore = asyncio.Semaphore(_max_full)
_snippet_semaphore = asyncio.Semaphore(_max_snippet)

# Track in-flight fire-and-forget analyses for start_analysis backpressure
_inflight_full_count = 0
_inflight_full_lock = asyncio.Lock()

_shutdown_event = asyncio.Event()


def shutdown_analyzer() -> None:
    """Shutdown the analyzer gracefully."""
    log.info("Shutting down analyzer...")
    _shutdown_event.set()
    _snippet_executor.shutdown(wait=True, cancel_futures=False)
    _full_executor.shutdown(wait=True, cancel_futures=False)
    cleanup_connections()
    log.info("Analyzer shutdown complete")


def _run_engine(engine, text: str) -> EngineResult:
    return engine.analyze(text)


def get_engine_list() -> list[tuple[str, str, str]]:
    """Return (key, name, description) for all engines in order."""
    return [(key, eng.name, eng.description) for key, eng in _engines]


def get_engine_list_rich() -> list[dict]:
    """Return full engine metadata for API and template rendering."""
    return [
        {
            "key": key,
            "name": eng.name,
            "description": eng.description,
            "code": eng.code,
            "engine_type": eng.engine_type,
            "url": eng.url,
        }
        for key, eng in _engines
    ]


async def start_analysis(
    text: str, source_type: str = "text", source: str = "", _queue_managed: bool = False
) -> tuple[str, bool]:
    """Start analysis and return (report_id, is_cached). Results stream via queue.

    When _queue_managed=True the caller (QueueManager) already tracks concurrency,
    so the internal _inflight_full_count gate is skipped.
    """
    global _inflight_full_count

    text_hash = compute_text_hash(text)

    # Check cache first
    if CACHE_ENABLED:
        cached_report = await get_report_by_hash(text_hash)
        if cached_report:
            log.debug(f"Cache hit for hash {text_hash[:16]}...")
            return cached_report.id, True

        # Check if there's already a pending analysis for this text
        pending_id = await get_pending_report_by_hash(text_hash)
        if pending_id:
            async with _pending_lock:
                if pending_id in _pending:
                    log.debug(f"Joining pending analysis {pending_id}")
                    return pending_id, False

    # Backpressure: reject if too many full analyses in flight
    # Skipped when queue manager handles concurrency externally
    if not _queue_managed:
        async with _inflight_full_lock:
            if _inflight_full_count >= _max_full:
                raise ValueError(
                    "Server busy — too many concurrent full analyses. Please retry shortly."
                )
            _inflight_full_count += 1
    else:
        async with _inflight_full_lock:
            _inflight_full_count += 1

    report_id = uuid.uuid4().hex[:12]
    word_count = len(text.split())

    # Create report in database
    try:
        await create_report(
            report_id=report_id,
            text_hash=text_hash,
            source_type=source_type,
            source=source if source else text[:100],
            text_excerpt=text[:2000],
            word_count=word_count,
            engines_total=len(_engines),
        )
    except Exception as e:
        async with _inflight_full_lock:
            _inflight_full_count -= 1
        log.error(f"Failed to create report: {e}")
        raise

    # Create a queue for streaming results
    queue: asyncio.Queue = asyncio.Queue()
    async with _pending_lock:
        _pending[report_id] = queue
        _result_counts[report_id] = 0

    log.info(f"Starting analysis {report_id} ({word_count} words)")

    # Launch all engines using full executor
    loop = asyncio.get_event_loop()
    for key, engine in _engines:
        future = loop.run_in_executor(_full_executor, _run_engine, engine, text)
        future.add_done_callback(
            lambda f, k=key, q=queue, rid=report_id: _on_engine_done(f, k, q, rid)
        )

    return report_id, False


def _on_engine_done(future, key: str, queue: asyncio.Queue, report_id: str):
    """Callback when a single engine finishes — push result to the queue."""
    try:
        result = future.result()
    except Exception as e:
        log.warning(f"Engine {key} failed for report {report_id}: {e}")
        result = EngineResult(
            engine_name=key,
            score=0.0,
            verdict=score_to_engine_verdict(0.0),
            details=f"Engine error: {type(e).__name__}",
            description="",
        )

    # Insert engine result into database
    try:
        insert_engine_result_sync(
            report_id=report_id,
            engine_key=key,
            engine_name=result.engine_name,
            score=result.score,
            verdict=result.verdict.value,
            details=result.details,
            description=result.description,
        )
    except Exception as e:
        log.error(f"Failed to insert engine result: {e}")

    # Update result count and calculate scores
    _result_counts[report_id] = _result_counts.get(report_id, 0) + 1
    try:
        _update_report_score_sync(report_id)
    except Exception as e:
        log.error(f"Failed to update report score: {e}")

    # Push to queue (thread-safe)
    try:
        queue.put_nowait((key, result))
    except Exception:
        pass


def _update_report_score_sync(report_id: str):
    """Recalculate overall score from database engine results using calibration."""
    from app.database import get_sync_connection

    conn = get_sync_connection()
    cursor = conn.execute(
        "SELECT engine_key, score FROM engine_results WHERE report_id = ?",
        (report_id,),
    )
    rows = cursor.fetchall()

    score_map = {row["engine_key"]: row["score"] for row in rows}

    # Fetch text for human signal scoring
    text_row = conn.execute(
        "SELECT text_excerpt FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    text = text_row["text_excerpt"] if text_row else ""

    # Build a lightweight result_map compatible with _calculate_full_calibrated_score
    class _ScoreObj:
        __slots__ = ("score",)

        def __init__(self, s):
            self.score = s

    result_map = {k: _ScoreObj(v) for k, v in score_map.items()}

    overall_score, _conf = _calculate_full_calibrated_score(result_map, text)

    overall_verdict = score_to_verdict_str(overall_score)
    engines_flagged = sum(1 for score in score_map.values() if score >= 0.4)

    update_report_score_sync(report_id, overall_score, overall_verdict, engines_flagged)


async def stream_results(
    report_id: str,
) -> AsyncGenerator[tuple[str, EngineResult, AnalysisReport], None]:
    """Yield (key, result, updated_report) as each engine completes."""
    async with _pending_lock:
        queue = _pending.get(report_id)

    if not queue:
        return

    received = 0
    total = len(_engines)
    while received < total:
        try:
            key, result = await asyncio.wait_for(queue.get(), timeout=300)
            received += 1
            report = await db_get_report(report_id)
            if report:
                yield key, result, report
        except asyncio.TimeoutError:
            log.warning(f"Timeout waiting for engine results on {report_id}")
            break
        except asyncio.CancelledError:
            log.info(f"Stream cancelled for {report_id}")
            break

    # Cleanup
    global _inflight_full_count
    async with _pending_lock:
        _pending.pop(report_id, None)
        _result_counts.pop(report_id, None)

    # Release inflight slot
    async with _inflight_full_lock:
        _inflight_full_count = max(0, _inflight_full_count - 1)

    # Mark report as complete (enables future cache hits)
    try:
        await mark_report_complete(report_id)
        log.info(f"Analysis {report_id} complete")
    except Exception as e:
        log.error(f"Failed to mark report complete: {e}")

    try:
        from app.engines.gpt2_cache import clear_caches

        clear_caches()
    except Exception:
        pass


# Keep the old synchronous-style API for /api/analyze (still async underneath)
async def analyze_text(
    text: str, source_type: str = "text", source: str = ""
) -> AnalysisReport:
    """Run all engines on the text and produce an aggregated report."""
    async with _full_semaphore:
        return await _analyze_text_inner(text, source_type, source)


async def _analyze_text_inner(
    text: str, source_type: str, source: str
) -> AnalysisReport:
    text_hash = compute_text_hash(text)

    # Check cache first
    if CACHE_ENABLED:
        cached_report = await get_report_by_hash(text_hash)
        if cached_report:
            log.debug(f"Cache hit for API request (hash {text_hash[:16]}...)")
            return cached_report

    loop = asyncio.get_event_loop()

    futures = []
    for key, engine in _engines:
        futures.append(
            (key, loop.run_in_executor(_full_executor, _run_engine, engine, text))
        )

    results: list[EngineResult] = []
    result_map: dict[str, EngineResult] = {}
    for key, future in futures:
        try:
            result = await future
        except Exception as e:
            log.warning(f"Engine {key} failed: {e}")
            result = EngineResult(
                engine_name=key,
                score=0.0,
                verdict=score_to_engine_verdict(0.0),
                details=f"Engine error: {type(e).__name__}",
                description="",
            )
        results.append(result)
        result_map[key] = result

    overall_score, _confidence = _calculate_full_calibrated_score(result_map, text)

    engines_flagged = sum(1 for r in results if r.score >= 0.4)

    report_id = uuid.uuid4().hex[:12]
    word_count = len(text.split())

    # Create report in database
    await create_report(
        report_id=report_id,
        text_hash=text_hash,
        source_type=source_type,
        source=source if source else text[:100],
        text_excerpt=text[:2000],
        word_count=word_count,
        engines_total=len(_engines),
    )

    # Insert all engine results
    for key, result in result_map.items():
        try:
            insert_engine_result_sync(
                report_id=report_id,
                engine_key=key,
                engine_name=result.engine_name,
                score=result.score,
                verdict=result.verdict.value,
                details=result.details,
                description=result.description,
            )
        except Exception as e:
            log.error(f"Failed to insert engine result: {e}")

    # Update scores and mark complete
    update_report_score_sync(
        report_id, overall_score, score_to_verdict_str(overall_score), engines_flagged
    )
    await mark_report_complete(report_id)

    report = await db_get_report(report_id)
    if not report:
        raise RuntimeError(f"Failed to retrieve created report {report_id}")
    return report


async def get_report(report_id: str) -> AnalysisReport | None:
    return await db_get_report(report_id)


async def get_recent_reports(limit: int = 10) -> list[AnalysisReport]:
    """Return the most recent completed reports (newest first)."""
    return await db_get_recent_reports(limit)


# --- Quick Score API for Chrome Extension ---


def _human_signal_score(text: str) -> float:
    """Detect human-writing signals that ML models miss.

    Returns a value in [-0.15, +0.10]:
      negative = text has human markers (pull score down)
      positive = text has AI markers (pull score up)
      zero = no signal

    Human signals: contractions, first-person, slang, typo patterns,
    varied punctuation, parenthetical asides, sentence fragments.

    AI signals: formulaic transitions, list patterns, hedging phrases,
    "as a" / "it's important to note" / "in conclusion" patterns.
    """
    import re

    if not text or len(text) < 50:
        return 0.0

    words = text.lower().split()
    n_words = len(words)
    if n_words < 10:
        return 0.0

    human_points = 0.0
    ai_points = 0.0

    # ── Human signals ──

    # Contractions (AI rarely uses them in formal text)
    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    if contractions >= 2:
        human_points += 0.06
    elif contractions >= 1:
        human_points += 0.03

    # First person casual voice
    first_person = sum(
        1 for w in words if w in ("i", "my", "me", "i'm", "i've", "i'd", "i'll")
    )
    if first_person >= 3:
        human_points += 0.05
    elif first_person >= 1:
        human_points += 0.02

    # Informal/slang markers
    informal = sum(
        1
        for w in words
        if w
        in (
            "lol",
            "lmao",
            "tbh",
            "imo",
            "imho",
            "gonna",
            "wanna",
            "gotta",
            "kinda",
            "sorta",
            "tho",
            "tho",
            "btw",
            "ngl",
            "fr",
            "lowkey",
            "highkey",
            "bruh",
            "nah",
            "yep",
            "yeah",
            "ok",
            "okay",
            "haha",
            "heh",
            "hmm",
            "ugh",
            "omg",
            "smh",
            "lmfao",
            "bc",
            "prolly",
        )
    )
    if informal >= 2:
        human_points += 0.08
    elif informal >= 1:
        human_points += 0.04

    # Parenthetical asides (human habit)
    parens = text.count("(") + text.count(")")
    dashes_aside = len(re.findall(r" - | — |--", text))
    if parens >= 2 or dashes_aside >= 2:
        human_points += 0.03

    # ── AI signals ──

    # Formulaic transition phrases
    ai_transitions = sum(
        1
        for phrase in [
            "it is important to note",
            "it is worth noting",
            "in today's world",
            "in today's digital",
            "plays a crucial role",
            "plays a vital role",
            "has revolutionized",
            "has transformed the way",
            "in conclusion,",
            "to summarize,",
            "here are",
            "here is a",
            "let me explain",
            "let me break",
            "this is a great question",
            "i hope this helps",
            "feel free to",
            "don't hesitate to",
        ]
        if phrase in text.lower()
    )
    if ai_transitions >= 2:
        ai_points += 0.08
    elif ai_transitions >= 1:
        ai_points += 0.04

    # Numbered/bulleted list patterns
    list_markers = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-*•])\s", text))
    if list_markers >= 3:
        ai_points += 0.05

    # "Firstly/Secondly/Additionally/Furthermore/Moreover" stacking
    connector_words = sum(
        1
        for w in words
        if w.rstrip(",")
        in (
            "firstly",
            "secondly",
            "thirdly",
            "additionally",
            "furthermore",
            "moreover",
            "consequently",
            "subsequently",
        )
    )
    if connector_words >= 2:
        ai_points += 0.04

    return min(ai_points, 0.10) - min(human_points, 0.15)


def _calculate_calibrated_score(
    results: dict[str, float], text: str = ""
) -> tuple[float, str]:
    """
    Calculate calibrated score using Fakespot as primary anchor.

    Empirical engine accuracy (MAGE hard eval):
      Fakespot: human=48%, AI=80% (gap=32%) — best discriminator
      E5:       human=79%, AI=89% (gap=10%) — over-triggers on formal text
      BERT:     human=77%, AI=84% (gap=7%)  — over-triggers on formal text
      TMR:      human=80%, AI=81% (gap=1%)  — almost no discrimination

    Strategy: Fakespot-dominant weighted average, then pull toward
    uncertain when all engines agree on high scores (formal text problem).

    Returns: (score 0-100, confidence: high/medium/low)
    """
    fakespot = results.get("classifier_fakespot", 0.5)
    tmr = results.get("classifier_tmr", 0.5)
    bert = results.get("classifier_bert_raid", 0.5)
    e5 = results.get("classifier_e5", 0.5)

    others = [tmr, bert, e5]
    others_avg = sum(others) / len(others) if others else 0.5

    # ── Step 1: Fakespot-dominant weighted score ──
    if fakespot < 0.35:
        # Fakespot confident human
        if others_avg < 0.50:
            score = fakespot * 0.50 + others_avg * 0.50
            confidence = "high"
        else:
            # Others disagree — formal writing pattern, trust Fakespot
            score = fakespot * 0.80 + others_avg * 0.20
            score = min(score, 0.40)
            confidence = "low"
    elif fakespot > 0.75:
        # Fakespot confident AI
        if others_avg > 0.60:
            score = fakespot * 0.50 + others_avg * 0.50
            confidence = "high"
        else:
            score = fakespot * 0.60 + others_avg * 0.40
            confidence = "medium"
    else:
        # Fakespot uncertain (0.35-0.75)
        score = fakespot * 0.60 + others_avg * 0.40
        confidence = "low"

    # ── Step 2: Linguistic/formulaic signal ──
    # These detect AI-specific phrases ("delve", "multifaceted") and structural
    # patterns ("in today's rapidly evolving"). Pure regex, independent of ML.
    ling_score = results.get("linguistic", 0.0)
    form_score = results.get("formulaic", 0.0)
    heuristic_signal = max(ling_score, form_score)  # 0.0-1.0

    # ── Step 3: Agreement-based correction ──
    # When ALL engines give very high scores (>0.85), this is suspicious
    # of the formal-text false positive pattern. Apply skepticism.
    all_scores = [fakespot, tmr, bert, e5]
    min_score = min(all_scores)
    max_score = max(all_scores)
    spread = max_score - min_score

    if min_score > 0.85 and spread < 0.15:
        # Suspiciously unanimous high scores — formal text pattern
        # Use linguistic/formulaic to differentiate: real AI text has markers
        if heuristic_signal > 0.3:
            # Has AI linguistic markers — probably actually AI
            score = score * 0.55 + 0.50 * 0.45
            confidence = "low"
        else:
            # No AI markers — likely formal human text
            score = score * 0.25 + 0.45 * 0.75
            confidence = "low"
    elif min_score > 0.75 and spread < 0.25:
        if heuristic_signal > 0.3:
            score = score * 0.75 + 0.50 * 0.25
            confidence = "low"
        else:
            score = score * 0.55 + 0.45 * 0.45
            confidence = "low"

    # ── Step 3b: "No markers" penalty ──
    # When score is high but NO AI markers detected, the ML classifiers
    # are likely wrong. This catches cases where 3/4 classifiers trigger
    # but the text has no linguistic/formulaic AI signal.
    if score > 0.55 and heuristic_signal < 0.05:
        # High ML score but zero AI markers — penalize proportionally
        penalty = (score - 0.55) * 0.35  # Reduce excess above 55% by 35%
        score = score - penalty
        if confidence == "high":
            confidence = "medium"

    # ── Step 4: Human signal adjustment ──
    if text:
        signal = _human_signal_score(text)
        if signal != 0:
            score = score + signal  # signal is [-0.15, +0.10]
            score = max(0.0, min(1.0, score))

    return round(min(max(score * 100, 0), 100), 1), confidence


def _calculate_full_calibrated_score(
    result_map: dict[str, "EngineResult"], text: str = ""
) -> tuple[float, str]:
    """
    Calibrated scoring for the full 21-engine pipeline.

    Uses the weighted average from ENGINE_WEIGHTS as a baseline, then applies
    Fakespot-dominant correction, unanimous-high skepticism, and linguistic/
    formulaic signal — the same calibration strategy as quick-score.
    """
    # Step 1: Compute weighted average baseline
    weighted_sum = 0.0
    weight_total = 0.0
    for key, weight in ENGINE_WEIGHTS.items():
        if key in result_map:
            weighted_sum += result_map[key].score * weight
            weight_total += weight

    baseline = (weighted_sum / weight_total) if weight_total > 0 else 0.5

    # Step 2: Extract 4 hot classifier scores for calibration
    fakespot = (
        result_map["classifier_fakespot"].score
        if "classifier_fakespot" in result_map
        else 0.5
    )
    tmr = result_map["classifier_tmr"].score if "classifier_tmr" in result_map else 0.5
    bert = (
        result_map["classifier_bert_raid"].score
        if "classifier_bert_raid" in result_map
        else 0.5
    )
    e5 = result_map["classifier_e5"].score if "classifier_e5" in result_map else 0.5

    # Get linguistic/formulaic signal
    ling_score = result_map["linguistic"].score if "linguistic" in result_map else 0.0
    form_score = result_map["formulaic"].score if "formulaic" in result_map else 0.0
    heuristic_signal = max(ling_score, form_score)

    # Step 3: Fakespot-dominant correction
    # Blend between baseline (all 21 engines) and Fakespot-anchored calibration
    others_avg = (tmr + bert + e5) / 3

    if fakespot < 0.35:
        # Fakespot confident human — trust it
        if others_avg < 0.50:
            calibrated = fakespot * 0.40 + others_avg * 0.30 + baseline * 0.30
            confidence = "high"
        else:
            calibrated = fakespot * 0.60 + others_avg * 0.15 + baseline * 0.25
            calibrated = min(calibrated, 0.40)
            confidence = "low"
    elif fakespot > 0.75:
        # Fakespot confident AI
        if others_avg > 0.60:
            calibrated = fakespot * 0.35 + others_avg * 0.30 + baseline * 0.35
            confidence = "high"
        else:
            calibrated = fakespot * 0.45 + others_avg * 0.25 + baseline * 0.30
            confidence = "medium"
    else:
        # Fakespot uncertain
        calibrated = fakespot * 0.40 + others_avg * 0.25 + baseline * 0.35
        confidence = "low"

    score = calibrated

    # Step 4: Unanimous-high skepticism
    ml_scores = [fakespot, tmr, bert, e5]
    min_ml = min(ml_scores)
    max_ml = max(ml_scores)
    spread = max_ml - min_ml

    if min_ml > 0.85 and spread < 0.15:
        if heuristic_signal > 0.3:
            score = score * 0.55 + 0.50 * 0.45
            confidence = "low"
        else:
            score = score * 0.25 + 0.45 * 0.75
            confidence = "low"
    elif min_ml > 0.75 and spread < 0.25:
        if heuristic_signal > 0.3:
            score = score * 0.75 + 0.50 * 0.25
            confidence = "low"
        else:
            score = score * 0.55 + 0.45 * 0.45
            confidence = "low"

    # Step 4b: "No markers" penalty
    if score > 0.55 and heuristic_signal < 0.05:
        penalty = (score - 0.55) * 0.35
        score = score - penalty
        if confidence == "high":
            confidence = "medium"

    # Step 5: Human signal adjustment
    if text:
        signal = _human_signal_score(text)
        if signal != 0:
            score = score + signal
            score = max(0.0, min(1.0, score))

    return round(min(max(score * 100, 0), 100), 1), confidence


async def quick_analyze_text(text: str) -> dict:
    """
    Fast analysis using only the 4 best ML classifiers.
    Returns score in ~300-500ms instead of 2-7s.
    Uses calibrated scoring with Fakespot as anchor.
    """
    async with _snippet_semaphore:
        return await _quick_analyze_text_inner(text)


async def _quick_analyze_text_inner(text: str) -> dict:
    import time

    start_time = time.perf_counter()

    loop = asyncio.get_event_loop()

    # Run all 4 quick engines in parallel
    futures = []
    for key, engine in _quick_engines:
        futures.append(
            (key, loop.run_in_executor(_snippet_executor, _run_engine, engine, text))
        )

    results: dict[str, float] = {}
    engine_details: list[dict] = []

    for key, future in futures:
        try:
            result = await future
            results[key] = result.score
            engine_details.append(
                {
                    "engine": key,
                    "score": round(result.score * 100, 1),
                    "verdict": result.verdict.value,
                }
            )
        except Exception as e:
            log.warning(f"Quick engine {key} failed: {e}")
            results[key] = 0.5  # Default to uncertain, not 0
            engine_details.append(
                {
                    "engine": key,
                    "score": 50.0,
                    "verdict": "error",
                }
            )

    # Calculate calibrated score
    overall_score, confidence = _calculate_calibrated_score(results, text)

    # Determine verdict based on calibrated score
    if overall_score <= 35:
        verdict = "clean"
    elif overall_score <= 65:
        verdict = "mixed"
    else:
        verdict = "ai"

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return {
        "score": overall_score,
        "verdict": verdict,
        "confidence": confidence,
        "engines": engine_details,
        "elapsed_ms": round(elapsed_ms, 1),
    }


async def paragraph_analyze(text: str) -> dict:
    """
    Split text into paragraphs and score each individually.
    Detects mixed human/AI content (e.g. human intro + AI body).
    Returns per-paragraph scores + overall summary.
    """
    import time
    import re

    start_time = time.perf_counter()

    # Split into paragraphs by double newline, then fall back to single newlines
    raw_paragraphs = re.split(r"\n\s*\n", text.strip())
    if len(raw_paragraphs) == 1:
        raw_paragraphs = text.strip().split("\n")

    # If still one big block, split by sentence groups (~3 sentences per chunk)
    if len(raw_paragraphs) == 1 and len(text) > 300:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        raw_paragraphs = []
        chunk = []
        for s in sentences:
            chunk.append(s)
            if len(chunk) >= 3:
                raw_paragraphs.append(" ".join(chunk))
                chunk = []
        if chunk:
            raw_paragraphs.append(" ".join(chunk))

    # Filter out too-short paragraphs, merge tiny ones
    paragraphs = []
    buffer = ""
    for p in raw_paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(p) < 50:
            buffer = (buffer + " " + p).strip() if buffer else p
        else:
            if buffer:
                paragraphs.append((buffer + " " + p).strip())
                buffer = ""
            else:
                paragraphs.append(p)
    if buffer:
        if paragraphs:
            paragraphs[-1] = paragraphs[-1] + " " + buffer
        else:
            paragraphs.append(buffer)

    if not paragraphs:
        return {
            "paragraphs": [],
            "overall_score": 0,
            "overall_verdict": "clean",
            "paragraph_count": 0,
            "ai_paragraph_count": 0,
            "elapsed_ms": 0,
        }

    # Score each paragraph in parallel
    async def score_para(idx: int, para_text: str) -> dict:
        result = await quick_analyze_text(para_text)
        return {
            "index": idx,
            "text": para_text[:500],
            "char_count": len(para_text),
            "score": result["score"],
            "verdict": result["verdict"],
            "confidence": result["confidence"],
        }

    tasks = [score_para(i, p) for i, p in enumerate(paragraphs)]
    para_results = await asyncio.gather(*tasks)
    para_results = sorted(para_results, key=lambda x: x["index"])

    # Weighted overall score by character count
    total_chars = sum(p["char_count"] for p in para_results)
    if total_chars > 0:
        overall_score = (
            sum(p["score"] * p["char_count"] for p in para_results) / total_chars
        )
    else:
        overall_score = 0

    overall_score = round(overall_score, 1)
    ai_count = sum(1 for p in para_results if p["score"] > 65)

    if overall_score <= 35:
        overall_verdict = "clean"
    elif overall_score <= 65:
        overall_verdict = "mixed"
    else:
        overall_verdict = "ai"

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return {
        "paragraphs": para_results,
        "overall_score": overall_score,
        "overall_verdict": overall_verdict,
        "paragraph_count": len(para_results),
        "ai_paragraph_count": ai_count,
        "elapsed_ms": round(elapsed_ms, 1),
    }


async def quick_analyze_batch(texts: list[tuple[str, str]]) -> list[dict]:
    """
    Analyze multiple texts in parallel using quick engines.
    Input: list of (id, text) tuples
    Returns: list of {id, score, verdict, confidence, elapsed_ms}
    """
    import time

    start_time = time.perf_counter()

    async def analyze_one(item_id: str, text: str) -> dict:
        result = await quick_analyze_text(text)
        result["id"] = item_id
        return result

    tasks = [analyze_one(item_id, text) for item_id, text in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions
    output = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.error(f"Batch item {texts[i][0]} failed: {result}")
            output.append(
                {
                    "id": texts[i][0],
                    "score": 0,
                    "verdict": "error",
                    "confidence": "none",
                    "error": str(result),
                }
            )
        else:
            output.append(result)

    total_elapsed = (time.perf_counter() - start_time) * 1000
    log.info(f"Quick batch analysis: {len(texts)} items in {total_elapsed:.0f}ms")

    return output


# --- Page-Level Structural Analysis for URL Scanning ---

# Heuristic engines for page structural analysis (pure regex, <5ms)
_heuristic_engines = [
    ("linguistic", _linguistic_engine, 0.20),
    ("formulaic", _formulaic_engine, 0.25),
    ("structural", _structural_engine, 0.30),
    ("sentiment", _sentiment_engine, 0.10),
    ("vocabulary", _vocabulary_engine, 0.10),
    ("readability", _readability_engine, 0.05),
]


def _compute_dom_score(dom_features: dict) -> tuple[float, str]:
    """Compute a structural AI score from client-side DOM features.

    Returns (score 0.0-1.0, detail_string).
    High heading->list count and list density are strong AI formatting signals.
    """
    hl_count = dom_features.get("heading_list_count", 0)
    li_count = dom_features.get("li_count", 0)
    heading_count = dom_features.get("heading_count", 0)
    para_count = dom_features.get("paragraph_count", 0)
    content_ratio = dom_features.get("content_ratio", 0)

    score = 0.0
    parts = []

    # Heading->list patterns: AI loves "Heading: \n - item \n - item" structure
    if hl_count >= 5:
        score += 0.35
        parts.append(f"{hl_count} heading->list sections")
    elif hl_count >= 3:
        score += 0.20
        parts.append(f"{hl_count} heading->list sections")
    elif hl_count >= 1:
        score += 0.08

    # High list density relative to paragraphs
    if para_count > 0 and li_count > 0:
        li_ratio = li_count / para_count
        if li_ratio > 3.0:
            score += 0.25
            parts.append(f"list-heavy ({li_count} items/{para_count} paras)")
        elif li_ratio > 1.5:
            score += 0.12

    # Many headings relative to paragraphs (over-structured)
    if para_count > 0 and heading_count > 0:
        h_ratio = heading_count / para_count
        if h_ratio > 0.5 and heading_count >= 5:
            score += 0.15
            parts.append(f"over-structured ({heading_count} headings)")

    # Low content ratio suggests boilerplate-heavy page (less reliable signal)
    if content_ratio > 0 and content_ratio < 0.3:
        score += 0.05

    score = min(score, 1.0)
    detail = "; ".join(parts) if parts else "DOM features within normal range"
    return score, detail


def analyze_page_structure(
    text: str,
    html_features: dict | None = None,
    dom_features: dict | None = None,
) -> dict:
    """Run 6 heuristic engines on page text for structural AI signals.

    Pure regex/string analysis — <5ms on 4000ch text.
    When html_features is provided (Phase B server-side), adds HTML-derived signals.
    When dom_features is provided (Phase C client-side), adds DOM-derived signals.
    DOM features are preferred over html_features as they see the rendered state.

    Returns structural_score (0-100), per-engine scores, top signals, signal count.
    """
    if not text or len(text) < 50:
        return {
            "score": 0.0,
            "signals": {},
            "signal_count": 0,
            "top_signals": [],
        }

    weighted_sum = 0.0
    weight_total = 0.0
    signals = {}
    descriptions = []
    engines_above_threshold = 0

    for key, engine, weight in _heuristic_engines:
        try:
            result = engine.analyze(text)
            signals[key] = round(result.score, 4)
            weighted_sum += result.score * weight
            weight_total += weight
            if result.score > 0.30:
                engines_above_threshold += 1
            # Collect non-empty descriptions for top signals
            if result.score > 0.20 and result.details:
                descriptions.append((result.score, key, result.details))
        except Exception as e:
            log.warning(f"Heuristic engine {key} failed: {e}")
            signals[key] = 0.0

    # HTML features — logged for research but NOT included in scoring.
    # Lists, headings, and formatting are universal in structured web content.
    # Both AI content farms and documentation sites score 1.0 on these signals.
    # They don't discriminate AI from human — they detect "structured page."
    if html_features:
        word_count = max(len(text.split()), 1)
        li_count = html_features.get("list_items", 0)
        if li_count > 0:
            list_per_1k = (li_count / word_count) * 1000
            signals["html_lists"] = round(min(list_per_1k / 30.0, 1.0), 4)
        hl_sections = html_features.get("heading_list_sections", 0)
        if hl_sections > 0:
            signals["html_heading_list"] = round(min(hl_sections / 3.0, 1.0), 4)
        bold = html_features.get("bold_count", 0)
        headings = html_features.get("headings", 0)
        if bold + headings > 0:
            format_density = ((bold + headings) / word_count) * 1000
            signals["html_formatting"] = round(min(format_density / 10.0, 1.0), 4)

    # DOM features: logged for research but NOT included in scoring.
    # Same issue as HTML features — structured pages (docs, tutorials) look
    # identical to AI content farms on structural DOM metrics alone.
    if dom_features:
        dom_score, dom_detail = _compute_dom_score(dom_features)
        signals["dom"] = round(dom_score, 4)

    composite = (weighted_sum / weight_total * 100) if weight_total > 0 else 0.0
    composite = round(min(max(composite, 0), 100), 1)

    # Top 3 signals sorted by score descending
    descriptions.sort(key=lambda x: x[0], reverse=True)
    top_signals = [
        {"engine": d[1], "score": round(d[0] * 100, 1), "detail": d[2][:120]}
        for d in descriptions[:3]
    ]

    return {
        "score": composite,
        "signals": signals,
        "signal_count": engines_above_threshold,
        "top_signals": top_signals,
    }


def compute_gpt2_signals(text: str) -> dict | None:
    """Extract GPT-2 perplexity signals for URL scan blending.

    Returns burstiness CV, overall perplexity, and GLTR-style token rank
    percentages — or None if text is too short / model fails.
    """
    import math
    import re
    import statistics
    import torch

    try:
        from app.engines.gpt2_cache import get_gpt2_outputs

        outputs = get_gpt2_outputs(text)
    except Exception as e:
        log.warning(f"GPT-2 signals failed: {e}")
        return None

    if outputs["logits"] is None or outputs["n_tokens"] < 10:
        return None

    logits = outputs["logits"]
    input_ids = outputs["input_ids"]
    n_tokens = outputs["n_tokens"]
    perplexity = math.exp(outputs["loss"]) if outputs["loss"] is not None else None

    # --- GLTR-style token rank percentages ---
    pred_logits = logits[0, :-1]
    actual_tokens = input_ids[0, 1:]
    actual_logit_vals = pred_logits.gather(1, actual_tokens.unsqueeze(1))
    ranks = (pred_logits > actual_logit_vals).sum(dim=-1)

    top10_pct = (ranks < 10).sum().item() / n_tokens
    top100_pct = (ranks < 100).sum().item() / n_tokens

    # --- Burstiness: per-sentence perplexity CV ---
    log_probs = torch.log_softmax(logits[0, :-1], dim=-1)
    token_losses = -log_probs.gather(1, actual_tokens.unsqueeze(1)).squeeze()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 5]

    burstiness_cv = None
    if len(sentences) >= 4:
        from app.engines.perplexity import _load_model

        _, tokenizer = _load_model()

        sentence_pps = []
        token_offset = 0
        full_token_count = token_losses.size(0)

        for sent in sentences:
            sent_tokens = tokenizer.encode(sent, add_special_tokens=False)
            sent_len = len(sent_tokens)
            if token_offset + sent_len > full_token_count:
                sent_len = full_token_count - token_offset
            if sent_len >= 4:
                sent_losses = token_losses[token_offset : token_offset + sent_len]
                mean_loss = sent_losses.mean().item()
                sentence_pps.append(math.exp(mean_loss))
            token_offset += sent_len
            if token_offset >= full_token_count:
                break

        if len(sentence_pps) >= 4:
            mean_pp = statistics.mean(sentence_pps)
            if mean_pp > 0:
                burstiness_cv = statistics.stdev(sentence_pps) / mean_pp

    return {
        "burstiness_cv": round(burstiness_cv, 4) if burstiness_cv is not None else None,
        "perplexity": round(perplexity, 2) if perplexity is not None else None,
        "top10_pct": round(top10_pct, 4),
        "top100_pct": round(top100_pct, 4),
    }


def _blend_fakespot_structural(
    fakespot_score: float,
    structural: dict,
    page_type: dict,
    text_len: int,
) -> tuple[float, str]:
    """Fakespot-primary scoring for URL scans, with structural as tiebreaker.

    Fakespot is the reliable ML signal. Structural analysis is only blended
    when Fakespot is near-zero and structural independently shows AI patterns.
    Otherwise, Fakespot score is used directly.

    Args:
        fakespot_score: 0-100 from _compute_fakespot_score
        structural: dict from analyze_page_structure()
        page_type: dict from classify_page_type()
        text_len: character count of the page text

    Returns: (blended_score 0-100, confidence)
    """
    # Non-scoreable pages: extension shows info badge
    if not page_type.get("scoreable", True):
        return 0.0, "none"

    # Reference/docs: Fakespot only (structural unreliable for code-heavy pages)
    if page_type.get("type") == "reference":
        return fakespot_score, "low"

    s_score = structural["score"]
    s_count = structural["signal_count"]

    # Only blend structural when Fakespot is low AND structural shows
    # AI writing patterns. Structural rarely exceeds 20%, so threshold is low.
    if fakespot_score <= 20 and s_score >= 12 and s_count >= 1:
        # Structural caught patterns Fakespot missed — let it nudge the score up
        # but cap at 50 (structural alone can't produce a "high" verdict)
        blended = fakespot_score * 0.40 + s_score * 0.60
        blended = min(blended, 50)
        return round(min(max(blended, 0), 100), 1), "low"

    # Everything else: trust Fakespot directly
    if fakespot_score >= 75 or fakespot_score <= 15:
        confidence = "high"
    else:
        confidence = "medium"

    return fakespot_score, confidence


# Keep old name as alias for backward compatibility in imports
def _blend_url_scores(
    ml_score: float,
    structural: dict,
    guard_hit: bool,
    text_len: int,
    gpt2_signals: dict | None = None,
) -> tuple[float, str]:
    """Legacy wrapper — redirects to _blend_fakespot_structural."""
    page_type = {"type": "article", "label": "Article", "scoreable": True}
    return _blend_fakespot_structural(ml_score, structural, page_type, text_len)


# --- Snippet Scan API (Ultra-fast for Google Search Results) ---


def _compute_fakespot_score(fakespot: float, text_len: int) -> tuple[float, str, str]:
    """Fakespot-only scoring for snippets and URL scans.

    Fakespot is the sole ML engine with genuine discriminative power
    (AI-vs-human gap of 0.229). BERT/E5/TMR detect formality, not AI.

    Returns (score 0-100, indicator, confidence).

    Thresholds:
      fakespot >= 0.85 → 75-90 (red, "Likely AI")
      fakespot >= 0.65 → 55-74 (yellow, "Maybe AI")
      fakespot >= 0.45 → 35-54 (yellow, "Uncertain")
      fakespot >= 0.25 → 15-34 (green, "Probably Human")
      fakespot < 0.25  → 0-14  (green, "Likely Human")

    Text length penalties:
      <150ch: cap 55%, confidence "low"
      150-299ch: cap 75%, confidence "medium"
      300ch+: full range
    """
    # Map fakespot raw (0-1) to score (0-100) with thresholds
    if fakespot >= 0.85:
        # Linear interpolation: 0.85→75, 1.0→90
        score = 75 + (fakespot - 0.85) / 0.15 * 15
    elif fakespot >= 0.65:
        # 0.65→55, 0.85→75
        score = 55 + (fakespot - 0.65) / 0.20 * 20
    elif fakespot >= 0.45:
        # 0.45→35, 0.65→55
        score = 35 + (fakespot - 0.45) / 0.20 * 20
    elif fakespot >= 0.25:
        # 0.25→15, 0.45→35
        score = 15 + (fakespot - 0.25) / 0.20 * 20
    else:
        # 0.0→0, 0.25→15
        score = fakespot / 0.25 * 15

    # Text length penalties
    if text_len < 150:
        score = min(score, 55)
        confidence = "low"
    elif text_len < 300:
        score = min(score, 75)
        confidence = "medium" if fakespot >= 0.50 else "low"
    else:
        confidence = "high" if fakespot >= 0.80 or fakespot < 0.20 else "medium"

    score = round(min(max(score, 0), 100), 1)

    if score >= 65:
        indicator = "red"
    elif score > 35:
        indicator = "yellow"
    else:
        indicator = "green"

    return score, indicator, confidence


async def scan_snippet(text: str) -> dict:
    """
    Fast analysis using Fakespot — the sole ML engine with discriminative power.
    Optimized for short snippets (~150 chars) from search results.
    Single engine, ~113ms latency.
    """
    import time

    start_time = time.perf_counter()

    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(
            _snippet_executor, _run_engine, _fakespot_engine, text
        )
        fakespot_raw = result.score
    except Exception as e:
        log.warning(f"Fakespot engine failed: {e}")
        fakespot_raw = 0.5

    score, indicator, confidence = _compute_fakespot_score(fakespot_raw, len(text))

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    return {
        "score": score,
        "indicator": indicator,
        "confidence": confidence,
        "elapsed_ms": round(elapsed_ms, 1),
    }


async def scan_snippets_batch(snippets: list[dict]) -> dict:
    """
    Batch scan multiple snippets using engine-level batching.
    Instead of N individual forward passes per engine, runs 1 batched pass.
    """
    async with _snippet_semaphore:
        return await _scan_snippets_batch_inner(snippets)


def _run_engine_batch_timed(engine, texts: list[str]) -> tuple[list[float], float]:
    """Run batch inference on an engine. Returns (scores, elapsed_ms)."""
    import time

    t0 = time.perf_counter()
    scores = engine.analyze_batch(texts)
    elapsed = (time.perf_counter() - t0) * 1000
    return scores, elapsed


async def _scan_snippets_batch_inner(snippets: list[dict]) -> dict:
    import time

    start_time = time.perf_counter()

    # Collect analyzable texts (>=20 chars), truncate to 500 chars for speed
    MAX_SNIPPET_CHARS = 500
    texts = []
    char_counts = []
    for s in snippets:
        text = s.get("text", "")
        if len(text) >= 20:
            texts.append(text[:MAX_SNIPPET_CHARS])
            char_counts.append(len(text))

    total_chars = sum(char_counts)
    fakespot_ms = 0.0

    # Run Fakespot only — single batched forward pass (~113ms for 5 texts)
    if texts:
        loop = asyncio.get_event_loop()
        fakespot_fut = loop.run_in_executor(
            _snippet_executor, _run_engine_batch_timed, _fakespot_engine, texts
        )

        try:
            fakespot_scores, fakespot_ms = await fakespot_fut
        except Exception as e:
            log.error(f"Fakespot batch failure: {e}")
            fakespot_scores = [0.5] * len(texts)
    else:
        fakespot_scores = []

    # Build results with per-snippet diagnostics
    output = []
    text_idx = 0
    for s in snippets:
        sid = s.get("id", "")
        surl = s.get("url", "")
        text = s.get("text", "")

        if len(text) < 20:
            output.append(
                {
                    "id": sid,
                    "url": surl,
                    "score": 50,
                    "indicator": "yellow",
                    "confidence": "none",
                    "chars": len(text),
                    "raw": {"fakespot": 0.5},
                }
            )
        else:
            f = fakespot_scores[text_idx]
            clen = char_counts[text_idx]
            score, indicator, confidence = _compute_fakespot_score(f, clen)
            output.append(
                {
                    "id": sid,
                    "url": surl,
                    "score": score,
                    "indicator": indicator,
                    "confidence": confidence,
                    "chars": clen,
                    "raw": {"fakespot": round(f, 4)},
                }
            )

            # Fire-and-forget scan logging
            scan_type = "url" if surl else "snippet"
            _text_for_hash = texts[text_idx]
            import hashlib

            _thash = hashlib.sha256(_text_for_hash.encode()).hexdigest()
            loop.run_in_executor(
                _snippet_executor,
                log_scan_sync,
                scan_type,
                text[:200],
                _thash,
                clen,
                score,
                indicator,
                confidence,
                0.0,
                0.0,
                0.0,
                f,
                False,
                "",
                surl,
                sid,
            )

            text_idx += 1

    total_elapsed = (time.perf_counter() - start_time) * 1000

    timing = {
        "total_ms": round(total_elapsed, 1),
        "fakespot_ms": round(fakespot_ms, 1),
        "texts": len(texts),
        "total_chars": total_chars,
        "avg_chars": round(total_chars / len(texts), 0) if texts else 0,
        "char_range": [
            min(char_counts) if char_counts else 0,
            max(char_counts) if char_counts else 0,
        ],
    }

    log.info(
        f"Snippet batch: {len(texts)} texts, {total_chars} chars "
        f"(avg {timing['avg_chars']:.0f}, range {timing['char_range'][0]}-{timing['char_range'][1]}) | "
        f"fakespot={fakespot_ms:.0f}ms | total={total_elapsed:.0f}ms"
    )

    return {
        "results": output,
        "total": len(snippets),
        "timing": timing,
    }
