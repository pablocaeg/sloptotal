import json
import logging

import httpx

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.responses import StreamingResponse

from app.config import SCORE_CLEAN, SCORE_LIKELY_AI, SCORE_LOW_RISK, SCORE_SUSPICIOUS
from app.schemas import WebAnalyzeRequest
from app.analyzer import (
    lane_for,
    start_analysis,
    wait_until_done,
    get_report,
    stream_results,
    get_engine_list,
    get_engine_list_rich,
)
from app.scraper import extract_text_from_url

log = logging.getLogger("sloptotal.routes.web")

router = APIRouter()

BANDS = [SCORE_CLEAN, SCORE_LOW_RISK, SCORE_SUSPICIOUS, SCORE_LIKELY_AI]

# The five verdicts in band order, with the reading shown on the home page.
BAND_INFO = [
    {
        "key": "clean",
        "label": "Clean, likely human-written",
        "desc": "Few AI signals across the engines. The text reads like human writing.",
    },
    {
        "key": "low",
        "label": "Low risk",
        "desc": "Some engines see minor signals. Formal or heavily polished human writing often lands here.",
    },
    {
        "key": "suspicious",
        "label": "Suspicious",
        "desc": "The engines disagree. It could be AI-assisted, edited AI output or formal human writing. A reason to look closer, not a conclusion.",
    },
    {
        "key": "likely",
        "label": "Likely AI-generated",
        "desc": "Strong signals from several engine families. Substantial AI generation with limited editing is likely.",
    },
    {
        "key": "slop",
        "label": "Slop detected",
        "desc": "Broad agreement across the engines: clear statistical and linguistic markers of unedited AI output.",
    },
]

SHORT_TEXT_WORDS = 80


def _index(request: Request, error: str = ""):
    engines = get_engine_list_rich()
    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {
            "engines": engines,
            "engine_count": len(engines),
            "bands": BANDS,
            "band_info": BAND_INFO,
            "error": error,
        },
    )


def _report_notes(report) -> list[str]:
    """Caveats shown above the breakdown: how far to trust this score."""
    notes = []
    if report.language_support == "unsupported":
        notes.append(
            "Detection does not work reliably in this text's language yet, so do not rely on this score."
        )
    elif report.language_support == "experimental":
        notes.append(
            "Detection in this language is experimental: it has been measured on far fewer texts than English, so read the score as a rough signal."
        )
    if report.word_count < SHORT_TEXT_WORDS:
        notes.append(
            "Under 80 words, this score is a weak signal: a short text swings on a few word choices."
        )
    if report.input_chars and report.input_chars > len(report.text_excerpt) + 1:
        notes.append(
            "Your text was longer than the analysis limit, so the analysis covers the part shown here."
        )
    return notes


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _index(request)


@router.post("/analyze")
async def analyze_form(
    request: Request, url: str = Form(default=""), text: str = Form(default="")
):
    """Handle form submission (no JavaScript): start analysis and redirect to the live report."""
    try:
        if url and url.strip():
            content = await extract_text_from_url(url.strip())
            report_id, is_cached = await start_analysis(
                content, source_type="url", source=url.strip()
            )
        elif text and text.strip():
            content = text.strip()
            if len(content) < 50:
                return _index(request, "Please provide at least 50 characters of text.")
            report_id, is_cached = await start_analysis(
                content, source_type="text", source=content[:100]
            )
        else:
            return _index(
                request, "Please provide a URL or paste some text to analyze."
            )
    except ValueError as e:
        return _index(request, str(e))
    except Exception as e:
        log.error(f"Analysis failed: {e}", exc_info=True)
        return _index(request, f"Analysis failed: {e}")

    return RedirectResponse(url=f"/report/{report_id}", status_code=303)


@router.post("/api/web/analyze")
async def api_web_analyze(request: Request, req: WebAnalyzeRequest):
    """Queue-aware endpoint for the web form.

    Returns JSON:
      200 {"status": "started", "report_id": "..."}  — immediate
      202 {"status": "queued", "ticket_id": ..., "position": ..., "estimated_wait_ms": ...}
      429 {"status": "rejected", ...}                 — queue full
      400 {"error": "..."}                            — validation error
    """
    queue_manager = request.app.state.queue_manager
    try:
        if req.url and req.url.strip():
            content = await extract_text_from_url(req.url.strip())
            source_type, source = "url", req.url.strip()
        elif req.text and req.text.strip():
            content = req.text.strip()
            if len(content) < 50:
                return JSONResponse(
                    {"error": "Please provide at least 50 characters of text."},
                    status_code=400,
                )
            source_type, source = "text", content[:100]
        else:
            return JSONResponse(
                {"error": "Please provide a URL or paste some text to analyze."},
                status_code=400,
            )

        if not queue_manager:
            report_id, is_cached = await start_analysis(
                content, source_type=source_type, source=source
            )
            return {"status": "started", "report_id": report_id}

        from app.cache import compute_text_hash

        text_hash = compute_text_hash(content)

        async def _execute(payload):
            rid, cached = await start_analysis(
                payload["text"],
                source_type=payload["source_type"],
                source=payload["source"],
                _queue_managed=True,
                lane=payload["lane"],
            )
            if cached:
                return {"report_id": rid}
            return {"report_id": rid, "_hold": wait_until_done(rid)}

        lane = lane_for(content)
        resp = await queue_manager.submit(
            lane,
            {
                "text": content,
                "source_type": source_type,
                "source": source,
                "lane": lane,
            },
            text_hash,
            _execute,
        )

        if resp["status"] == "completed":
            return {"status": "started", "report_id": resp["result"]["report_id"]}
        elif resp["status"] == "queued":
            return JSONResponse(resp, status_code=202)
        elif resp["status"] == "rejected":
            return JSONResponse(
                {"error": resp["error"], "retry_after": resp.get("retry_after", 5)},
                status_code=429,
            )
        elif resp["status"] == "error":
            err = resp.get("error", "")
            if "busy" in err.lower():
                return JSONResponse({"error": err, "retry_after": 2}, status_code=429)
            return JSONResponse({"error": err or "Analysis failed"}, status_code=500)
        else:
            return JSONResponse(
                {"error": resp.get("error", "Unknown error")}, status_code=500
            )
    except ValueError as e:
        if "busy" in str(e).lower():
            return JSONResponse({"error": str(e), "retry_after": 2}, status_code=429)
        return JSONResponse({"error": str(e)}, status_code=400)
    except httpx.HTTPError as e:
        log.info(f"Web analyze could not fetch {req.url}: {e!r}")
        return JSONResponse({"error": "Could not fetch that URL."}, status_code=502)
    except Exception as e:
        log.error(f"Web analyze failed: {e}", exc_info=True)
        return JSONResponse(
            {"error": "Analysis failed. Please try again."}, status_code=500
        )


@router.get("/report/{report_id}", response_class=HTMLResponse)
async def report_page(request: Request, report_id: str):
    templates = request.app.state.templates
    if not report_id or len(report_id) > 12 or not report_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid report ID")

    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    engines = get_engine_list_rich()
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "report": report,
            "engines": engines,
            "engine_count": len(engines),
            "bands": BANDS,
            "band_info": BAND_INFO,
            "notes": _report_notes(report),
        },
    )


@router.get("/api/stream/{report_id}")
async def sse_stream(report_id: str):
    """Server-Sent Events endpoint — streams engine results as they complete."""
    if not report_id or len(report_id) > 12 or not report_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid report ID")

    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    async def event_generator():
        has_stream = False
        try:
            async for key, result, updated_report in stream_results(report_id):
                has_stream = True
                data = json.dumps(
                    {
                        "key": key,
                        "engine_name": result.engine_name,
                        "score": result.score,
                        "verdict": result.verdict.value,
                        "details": result.details,
                        "description": result.description,
                        "overall_score": updated_report.overall_score,
                        "overall_verdict": updated_report.overall_verdict,
                        "engines_flagged": updated_report.engines_flagged,
                        "engines_total": updated_report.engines_total,
                        "engines_done": len(updated_report.engine_results),
                    }
                )
                yield f"data: {data}\n\n"
        except Exception as e:
            log.error(f"Error in SSE stream: {e}")

        # If no stream was available (analysis already finished), replay stored results
        if not has_stream and report.engine_results:
            for result in report.engine_results:
                eng_key = ""
                for ek, ename, _ in get_engine_list():
                    if ename == result.engine_name:
                        eng_key = ek
                        break
                data = json.dumps(
                    {
                        "key": eng_key,
                        "engine_name": result.engine_name,
                        "score": result.score,
                        "verdict": result.verdict.value,
                        "details": result.details,
                        "description": result.description,
                        "overall_score": report.overall_score,
                        "overall_verdict": report.overall_verdict,
                        "engines_flagged": report.engines_flagged,
                        "engines_total": report.engines_total,
                        "engines_done": len(report.engine_results),
                    }
                )
                yield f"data: {data}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
