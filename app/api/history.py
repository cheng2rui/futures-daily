from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.history_backfill import MAX_BACKFILL_DAYS, backfill_history, recent_weekdays
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/backfill-plan")
def backfill_plan(end_date: str | None = None, days: int = Query(default=5, ge=1, le=MAX_BACKFILL_DAYS)):
    end = normalize_trade_date(end_date)
    return {"end_date": end, "days": days, "dates": recent_weekdays(end, days), "max_days": MAX_BACKFILL_DAYS}


@router.post("/backfill")
def run_backfill(
    end_date: str | None = None,
    days: int = Query(default=5, ge=1, le=MAX_BACKFILL_DAYS),
    seats: bool = False,
    enhancements: bool = True,
    rebuild_latest: bool = True,
    db: Session = Depends(get_db),
):
    return backfill_history(
        db,
        end_date=end_date,
        days=days,
        collect_daily=True,
        collect_seats=seats,
        collect_enhancements=enhancements,
        rebuild_latest=rebuild_latest,
    )
