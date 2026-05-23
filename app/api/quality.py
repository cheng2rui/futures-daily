from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_quality import build_data_quality
from app.services.retry_planner import build_retry_plan
from app.services.retry_runner import run_retry_plan
from app.services.source_diagnostics import diagnose_weak_sources
from app.services.source_health import build_source_health
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/coverage/{trade_date}")
def get_coverage_matrix(trade_date: str, sync_gaps: bool = True, db: Session = Depends(get_db)):
    return build_coverage_matrix(db, normalize_trade_date(trade_date), sync_gaps=sync_gaps)


@router.get("/diagnostics/{trade_date}")
def get_source_diagnostics(trade_date: str, exchange: str | None = None, db: Session = Depends(get_db)):
    exchanges = [exchange] if exchange else None
    return diagnose_weak_sources(db, normalize_trade_date(trade_date), exchanges=exchanges)


@router.get("/source-health/{trade_date}")
def get_source_health(trade_date: str, db: Session = Depends(get_db)):
    return build_source_health(db, normalize_trade_date(trade_date))


@router.get("/retry-plan/{trade_date}")
def get_retry_plan(trade_date: str, db: Session = Depends(get_db)):
    return build_retry_plan(db, normalize_trade_date(trade_date))


@router.post("/retry-plan/{trade_date}/run")
def run_retry_plan_endpoint(
    trade_date: str,
    max_steps: int = 3,
    stop_on_failure: bool = False,
    rebuild: bool = True,
    db: Session = Depends(get_db),
):
    return run_retry_plan(db, normalize_trade_date(trade_date), max_steps=max_steps, stop_on_failure=stop_on_failure, rebuild=rebuild)


@router.get("/{trade_date}")
def get_quality(trade_date: str, db: Session = Depends(get_db)):
    quality = build_data_quality(db, normalize_trade_date(trade_date))
    quality["coverage_matrix"] = build_coverage_matrix(db, normalize_trade_date(trade_date), sync_gaps=False)
    return quality
