import json
import logging

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.responses import StreamingResponse

from app.schemas import WebAnalyzeRequest
from app.analyzer import (
    start_analysis,
    get_report,
    stream_results,
    get_engine_list,
    get_engine_list_rich,
    get_recent_reports,
)
from app.scraper import extract_text_from_url

log = logging.getLogger("sloptotal.routes.web")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    templates = request.app.state.templates
    try:
        recent = await get_recent_reports(limit=10)
    except Exception as e:
        log.error(f"Failed to get recent reports: {e}")
        recent = []
    engines = get_engine_list_rich()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recent_reports": recent,
            "engines": engines,
        },
    )


@router.post("/analyze")
async def analyze_form(
    request: Request, url: str = Form(default=""), text: str = Form(default="")
):
    """Handle form submission — start analysis and redirect to live report page."""
    templates = request.app.state.templates
    try:
        if url and url.strip():
            content = await extract_text_from_url(url.strip())
            report_id, is_cached = await start_analysis(
                content, source_type="url", source=url.strip()
            )
        elif text and text.strip():
            content = text.strip()
            if len(content) < 50:
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "error": "Please provide at least 50 characters of text.",
                    },
                )
            report_id, is_cached = await start_analysis(
                content, source_type="text", source=content[:100]
            )
        else:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "Please provide a URL or paste some text to analyze.",
                },
            )
    except ValueError as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(e),
            },
        )
    except Exception as e:
        log.error(f"Analysis failed: {e}", exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"Analysis failed: {e}",
            },
        )

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
            rid, _cached = await start_analysis(
                payload["text"],
                source_type=payload["source_type"],
                source=payload["source"],
                _queue_managed=True,
            )
            return {"report_id": rid}

        resp = await queue_manager.submit(
            "full",
            {"text": content, "source_type": source_type, "source": source},
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
    engines = get_engine_list()
    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "report": report,
            "engines": engines,
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
