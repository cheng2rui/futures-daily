from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.event_calendar import build_event_calendar
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/calendar")
def get_event_calendar(trade_date: str | None = None, window_days: int = Query(default=14, ge=1, le=60)):
    trade_date = normalize_trade_date(trade_date)
    return build_event_calendar(trade_date, window_days=window_days)
