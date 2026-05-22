from __future__ import annotations

from pathlib import Path
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import assistant, dataset, jobs, markets, quality, reports, seat_archive, seats, settings, watch
from app.db import init_db
from app.logging_config import setup_logging
from app.services.scheduler import start_scheduler, stop_scheduler

from app.version import VERSION

setup_logging()
logger = logging.getLogger("futures_daily")

app = FastAPI(title="Futures Daily", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception("request failed method=%s path=%s duration_ms=%s", request.method, request.url.path, duration_ms)
        raise
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    if request.url.path.startswith("/api"):
        logger.info("request method=%s path=%s status=%s duration_ms=%s", request.method, request.url.path, response.status_code, duration_ms)
    return response


app.include_router(assistant.router)
app.include_router(dataset.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(markets.router)
app.include_router(seat_archive.router)
app.include_router(quality.router)
app.include_router(seats.router)
app.include_router(settings.router)
app.include_router(watch.router)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("futures-daily starting version=%s", VERSION)
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    logger.info("futures-daily stopping version=%s", VERSION)
    stop_scheduler()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION}


WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "futures-daily", "message": "frontend not built yet"}
