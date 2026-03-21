import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import (
    AnalyzeRequest,
    SnippetBatchRequest,
    BatchUrlRequest,
    UrlScanRequest,
)
from app.analyzer import (
    analyze_text,
    get_report,
    get_recent_reports,
    get_engine_list_rich,
    quick_analyze_text,
    quick_analyze_batch,
    scan_snippets_batch,
    paragraph_analyze,
    analyze_page_structure,
    _blend_fakespot_structural,
    _quick_analyze_text_inner,
    _scan_snippets_batch_inner,
    _analyze_text_inner,
)
from app.database import get_scan_stats, log_scan_sync
from app.scraper import extract_text_from_url, extract_text_with_metadata
from app.page_classifier import classify_page_type

log = logging.getLogger("sloptotal.routes.api")

router = APIRouter(prefix="/api")


@router.post("/quick-score")
async def api_quick_score(request: Request, req: AnalyzeRequest):
    """Fast analysis using only 4 best ML classifiers."""
    queue_manager = request.app.state.queue_manager
    try:
        if req.url:
            content = await extract_text_from_url(req.url.strip())
        elif req.text:
            content = req.text.strip()
            if len(content) < 50:
                return JSONResponse(
                    {"error": "Text must be at least 50 characters."}, status_code=400
                )
        else:
            return JSONResponse(
                {"error": "Provide 'url' or 'text' field."}, status_code=400
            )

        if not queue_manager:
            result = await quick_analyze_text(content)
            return result

        from app.cache import compute_text_hash

        text_hash = compute_text_hash(content)

        async def _execute(payload):
            return await _quick_analyze_text_inner(payload)

        resp = await queue_manager.submit("quick", content, text_hash, _execute)

        if resp["status"] == "completed":
            return resp["result"]
        elif resp["status"] == "queued":
            return JSONResponse(resp, status_code=202)
        elif resp["status"] == "rejected":
            return JSONResponse(
                {"error": resp["error"], "retry_after": resp["retry_after"]},
                status_code=429,
            )
        else:
            return JSONResponse(
                {"error": resp.get("error", "Unknown error")}, status_code=500
            )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.error(f"Quick score failed: {e}", exc_info=True)
        return JSONResponse({"error": "Analysis failed"}, status_code=500)


@router.post("/paragraph-score")
async def api_paragraph_score(req: AnalyzeRequest):
    """Per-paragraph AI detection — splits text into paragraphs and scores each."""
    try:
        if req.url:
            content = await extract_text_from_url(req.url.strip())
        elif req.text:
            content = req.text.strip()
            if len(content) < 50:
                return JSONResponse(
                    {"error": "Text must be at least 50 characters."}, status_code=400
                )
        else:
            return JSONResponse(
                {"error": "Provide 'url' or 'text' field."}, status_code=400
            )

        result = await paragraph_analyze(content)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.error(f"Paragraph score failed: {e}", exc_info=True)
        return JSONResponse({"error": "Analysis failed"}, status_code=500)


@router.post("/scan/snippets")
async def api_scan_snippets(request: Request, req: SnippetBatchRequest):
    """Ultra-fast batch scan for Google search snippets."""
    queue_manager = request.app.state.queue_manager
    if not req.snippets or len(req.snippets) > 30:
        return JSONResponse({"error": "Provide 1-30 snippets"}, status_code=400)

    snippets_data = [{"id": s.id, "text": s.text, "url": s.url} for s in req.snippets]

    try:
        if not queue_manager:
            result = await scan_snippets_batch(snippets_data)
            return result

        import hashlib

        batch_hash = hashlib.sha256(
            "|".join(s["text"] for s in snippets_data).encode()
        ).hexdigest()[:16]

        async def _execute(payload):
            return await _scan_snippets_batch_inner(payload)

        resp = await queue_manager.submit(
            "snippet", snippets_data, batch_hash, _execute
        )

        if resp["status"] == "completed":
            return resp["result"]
        elif resp["status"] == "queued":
            return JSONResponse(resp, status_code=202)
        elif resp["status"] == "rejected":
            return JSONResponse(
                {"error": resp["error"], "retry_after": resp["retry_after"]},
                status_code=429,
            )
        else:
            return JSONResponse(
                {"error": resp.get("error", "Unknown error")}, status_code=500
            )
    except Exception as e:
        log.error(f"Snippet scan failed: {e}", exc_info=True)
        return JSONResponse({"error": "Scan failed"}, status_code=500)


@router.post("/scan/urls")
async def api_scan_urls(req: UrlScanRequest):
    """Fetch URL content, classify page type, run Fakespot + structural, blend.

    Per-URL flow:
    1. Fetch page content
    2. Classify page type (article/hub/landing/reference/short)
    3. Non-scoreable pages → info response (grey badge)
    4. Scoreable pages → Fakespot (500ch) + structural (4000ch) → blend → scored badge
    """
    import time
    import hashlib

    start_time = time.perf_counter()

    if not req.urls or len(req.urls) > 10:
        return JSONResponse({"error": "Provide 1-10 URLs"}, status_code=400)

    async def fetch_and_score(item):
        """Fetch one URL, classify, score if applicable."""
        t0 = time.perf_counter()
        try:
            page = await extract_text_with_metadata(item.url)
            fetch_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:
            fetch_ms = (time.perf_counter() - t0) * 1000
            return {
                "type": "error",
                "id": item.id,
                "url": item.url,
                "error": str(e),
                "fetch_ms": round(fetch_ms, 1),
            }

        if page.char_count < 50:
            return {
                "type": "error",
                "id": item.id,
                "url": item.url,
                "error": "Text too short",
                "fetch_ms": round(fetch_ms, 1),
            }

        # Classify page type
        page_type = classify_page_type(
            page.full_text,
            page.html_features,
            page.char_count,
            item.dom_features,
        )

        # Non-scoreable pages → info response
        if not page_type["scoreable"]:
            total_ms = (time.perf_counter() - t0) * 1000
            return {
                "type": "info",
                "id": item.id,
                "url": item.url,
                "page_type": page_type["type"],
                "page_label": page_type["label"],
                "scoreable": False,
                "chars": page.char_count,
                "fetch_ms": round(fetch_ms, 1),
                "item_ms": round(total_ms, 1),
            }

        # Scoreable pages: run Fakespot + structural in parallel
        snippet = [{"id": item.id, "text": page.ml_text, "url": item.url}]

        score_t0 = time.perf_counter()

        async def _ml_score():
            return await scan_snippets_batch(snippet)

        async def _structural():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                analyze_page_structure,
                page.heuristic_text,
                page.html_features,
                item.dom_features,
            )

        ml_result, structural = await asyncio.gather(_ml_score(), _structural())
        score_ms = (time.perf_counter() - score_t0) * 1000

        r = ml_result.get("results", [{}])[0]
        fakespot_score = r.get("score", 50)
        raw = r.get("raw", {})

        # Blend Fakespot + structural (page-type-aware)
        blended_score, blended_confidence = _blend_fakespot_structural(
            fakespot_score,
            structural,
            page_type,
            page.char_count,
        )

        # Determine final verdict
        if blended_score >= 65:
            indicator = "red"
        elif blended_score > 35:
            indicator = "yellow"
        else:
            indicator = "green"

        total_ms = (time.perf_counter() - t0) * 1000

        # Fire-and-forget scan logging
        loop = asyncio.get_event_loop()
        _thash = hashlib.sha256(page.ml_text.encode()).hexdigest()
        sigs = structural.get("signals", {})
        loop.run_in_executor(
            None,
            log_scan_sync,
            "url",
            page.ml_text[:200],
            _thash,
            page.char_count,
            blended_score,
            indicator,
            blended_confidence,
            0.0,
            0.0,
            0.0,
            raw.get("fakespot", 0.5),
            False,
            "",
            item.url,
            item.id,
            structural["score"],
            structural["signal_count"],
            sigs.get("linguistic"),
            sigs.get("formulaic"),
            sigs.get("structural"),
            sigs.get("vocabulary"),
            sigs.get("readability"),
            sigs.get("sentiment"),
            fakespot_score,
            True,
        )

        return {
            "type": "result",
            "id": item.id,
            "url": item.url,
            "score": blended_score,
            "indicator": indicator,
            "confidence": blended_confidence,
            "chars": page.char_count,
            "raw": raw,
            "ml_score": fakespot_score,
            "page_type": page_type["type"],
            "page_label": page_type["label"],
            "scoreable": True,
            "structural": {
                "score": structural["score"],
                "signal_count": structural["signal_count"],
                "top_signals": structural["top_signals"],
                "signals": structural["signals"],
            },
            "fetch_ms": round(fetch_ms, 1),
            "score_ms": round(score_ms, 1),
            "item_ms": round(total_ms, 1),
            "full_chars": page.char_count,
            "source": "url_content",
        }

    # Launch all fetch+score tasks in parallel
    all_results = await asyncio.gather(*[fetch_and_score(u) for u in req.urls])

    results = [r for r in all_results if r["type"] == "result"]
    info = [r for r in all_results if r["type"] == "info"]
    errors = [r for r in all_results if r["type"] == "error"]

    # Clean up type field
    for r in results:
        r.pop("type", None)
    for i in info:
        i.pop("type", None)
    for e in errors:
        e.pop("type", None)

    total_ms = (time.perf_counter() - start_time) * 1000

    return {
        "results": results,
        "info": info,
        "errors": errors,
        "timing": {
            "total_ms": round(total_ms, 1),
            "urls_total": len(req.urls),
            "urls_scored": len(results),
            "urls_info": len(info),
            "urls_failed": len(errors),
        },
    }


@router.post("/quick-score/batch")
async def api_quick_score_batch(req: BatchUrlRequest):
    """Batch quick analysis for multiple URLs."""
    import time

    start_time = time.perf_counter()

    if not req.urls or len(req.urls) > 20:
        return JSONResponse({"error": "Provide 1-20 URLs"}, status_code=400)

    async def fetch_url(url: str) -> tuple[str, str | None, str | None]:
        try:
            content = await extract_text_from_url(url.strip())
            return (url, content, None)
        except Exception as e:
            return (url, None, str(e))

    fetch_tasks = [fetch_url(url) for url in req.urls]
    fetch_results = await asyncio.gather(*fetch_tasks)

    texts_to_analyze = []
    errors = []
    for url, content, error in fetch_results:
        if error:
            errors.append({"url": url, "error": error})
        elif content:
            texts_to_analyze.append((url, content))

    if texts_to_analyze:
        results = await quick_analyze_batch(texts_to_analyze)
        for r in results:
            r["url"] = r.pop("id")
    else:
        results = []

    total_elapsed = (time.perf_counter() - start_time) * 1000

    return {
        "results": results,
        "errors": errors,
        "total_urls": len(req.urls),
        "successful": len(results),
        "failed": len(errors),
        "elapsed_ms": round(total_elapsed, 1),
    }


@router.post("/analyze")
async def api_analyze(request: Request, req: AnalyzeRequest):
    """JSON API endpoint for programmatic access."""
    queue_manager = request.app.state.queue_manager
    try:
        if req.url:
            content = await extract_text_from_url(req.url.strip())
            source_type, source = "url", req.url.strip()
        elif req.text:
            if len(req.text.strip()) < 50:
                return JSONResponse(
                    {"error": "Text must be at least 50 characters."}, status_code=400
                )
            content = req.text.strip()
            source_type, source = "text", content[:100]
        else:
            return JSONResponse(
                {"error": "Provide 'url' or 'text' field."}, status_code=400
            )

        if not queue_manager:
            report = await analyze_text(content, source_type=source_type, source=source)
            return report.model_dump()

        from app.cache import compute_text_hash

        text_hash = compute_text_hash(content)

        async def _execute(payload):
            report = await _analyze_text_inner(
                payload["text"], payload["source_type"], payload["source"]
            )
            return report.model_dump()

        resp = await queue_manager.submit(
            "full",
            {"text": content, "source_type": source_type, "source": source},
            text_hash,
            _execute,
        )

        if resp["status"] == "completed":
            return resp["result"]
        elif resp["status"] == "queued":
            return JSONResponse(resp, status_code=202)
        elif resp["status"] == "rejected":
            return JSONResponse(
                {"error": resp["error"], "retry_after": resp["retry_after"]},
                status_code=429,
            )
        else:
            return JSONResponse(
                {"error": resp.get("error", "Unknown error")}, status_code=500
            )
    except ValueError as e:
        if "busy" in str(e).lower():
            return JSONResponse({"error": str(e), "retry_after": 2}, status_code=429)
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        log.error(f"API analyze failed: {e}", exc_info=True)
        return JSONResponse({"error": "Analysis failed"}, status_code=500)


@router.get("/recent")
async def api_recent():
    """Return recent completed reports for the ticker."""
    try:
        reports = await get_recent_reports(limit=10)
        return [
            {
                "id": r.id,
                "source": r.source[:80],
                "source_type": r.source_type,
                "overall_score": r.overall_score,
                "overall_verdict": r.overall_verdict,
                "word_count": r.word_count,
                "created_at": r.created_at.strftime("%H:%M"),
            }
            for r in reports
        ]
    except Exception as e:
        log.error(f"Failed to get recent reports: {e}")
        return []


@router.get("/report/{report_id}")
async def api_report(report_id: str):
    if not report_id or len(report_id) > 12 or not report_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid report ID")

    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report.model_dump()


@router.get("/scan/stats")
async def api_scan_stats():
    """Return scan log statistics and recent scans for analysis."""
    try:
        return await get_scan_stats()
    except Exception as e:
        log.error(f"Failed to get scan stats: {e}")
        return JSONResponse({"error": "Failed to get stats"}, status_code=500)


@router.get("/engines")
async def api_engines():
    """Return metadata for all detection engines."""
    return get_engine_list_rich()
