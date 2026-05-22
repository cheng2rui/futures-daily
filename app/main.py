from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import assistant, dataset, jobs, markets, quality, reports, seat_archive, seats, settings, watch
from app.db import init_db
from app.services.scheduler import start_scheduler, stop_scheduler

from app.version import VERSION

app = FastAPI(title="Futures Daily", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
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
