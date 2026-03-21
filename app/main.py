import logging
import os
from contextlib import asynccontextmanager

# Auto-detect hardware and configure before any model loading.
# Explicit env vars (e.g. for production) always override autoconfig.
from app.autoconfig import run_autoconfig, format_banner, get_device

_hw, _profile, _config = run_autoconfig()

import torch

torch.set_num_threads(int(os.getenv("SLOPTOTAL_TORCH_THREADS", "1")))
torch.set_num_interop_threads(1)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR, STATIC_DIR
from app.database import init_database, check_database_health
from app.analyzer import get_engine_list, shutdown_analyzer, _max_full, _max_snippet
from app.queue_manager import QueueManager

from app.routes.web import router as web_router
from app.routes.api import router as api_router
from app.routes.queue import router as queue_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sloptotal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    print(format_banner(_hw, _profile, _config))
    log.info(f"Starting SlopTotal (profile={_profile}, device={get_device()})...")
    await init_database()
    _preload_models()

    queue_manager = QueueManager(
        max_snippet=_max_snippet,
        max_quick=_max_snippet,
        max_full=_max_full,
    )
    await queue_manager.start()
    app.state.queue_manager = queue_manager

    log.info("SlopTotal started")
    yield
    log.info("Shutting down SlopTotal...")
    await queue_manager.stop()
    shutdown_analyzer()
    log.info("SlopTotal shutdown complete")


app = FastAPI(
    title="SlopTotal",
    description="VirusTotal for AI slop detection",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://localhost(:\d+)?|https://sloptotal\.com|https://pablocaeg\.github\.io)$",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.state.queue_manager = None  # set in lifespan

# Include routers
app.include_router(web_router)
app.include_router(api_router)
app.include_router(queue_router)


def _preload_models():
    """Preload ML models in background thread."""
    import threading

    def _preload():
        loaders = [
            ("GPT-2 Medium", "app.engines.perplexity", "_load_model"),
            ("DistilGPT-2", "app.engines.cross_perplexity", "_load_distil_model"),
            ("OpenAI detector", "app.engines.classifier_openai", "_load_model"),
            ("ChatGPT detector", "app.engines.classifier_chatgpt", "_load_model"),
            ("ReMoDetect DeBERTa", "app.engines.classifier_remodetect", "_load_model"),
            ("Fakespot RoBERTa", "app.engines.classifier_fakespot", "_init_pool"),
            ("E5-Small LoRA", "app.engines.classifier_e5", "_init_pool"),
            ("TMR RoBERTa", "app.engines.classifier_tmr", "_init_pool"),
            ("BERT-tiny RAID", "app.engines.classifier_bert_raid", "_init_pool"),
            ("Desklib DeBERTa", "app.engines.classifier_desklib", "_load_model"),
            (
                "SuperAnnotate RoBERTa",
                "app.engines.classifier_superannotate",
                "_load_model",
            ),
        ]

        import importlib

        for name, module_path, func_name in loaders:
            try:
                mod = importlib.import_module(module_path)
                getattr(mod, func_name)()
                log.info(f"Preloaded {name}")
            except Exception as e:
                log.warning(f"{name} preload failed: {e}")

        log.info("Model preloading complete — 23 engines ready")

        # NOTE: GPT-2 Large (774M) is NOT pre-warmed here. It loads on-demand
        # for full analysis only. Loading it eagerly would add ~3-5s startup
        # and ~1.5GB RAM for signals that don't discriminate on scraped text.

    threading.Thread(target=_preload, daemon=True).start()


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    db_health = await check_database_health()
    resp = {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "database": db_health,
        "engines": len(get_engine_list()),
    }
    if app.state.queue_manager:
        resp["queue"] = app.state.queue_manager.queue_status()
    return resp


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
