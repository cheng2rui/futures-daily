from __future__ import annotations

from fastapi import APIRouter

from app.services.seat_archive import available_archive_dates, load_archive_history, load_archive_summary
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/seat-archive", tags=["seat-archive"])


@router.get("/dates")
def get_archive_dates():
    return {"dates": available_archive_dates()}


@router.get("/{trade_date}")
def get_seat_archive(trade_date: str):
    return load_archive_summary(normalize_trade_date(trade_date))


@router.get("/{trade_date}/history")
def get_seat_archive_history(trade_date: str, days: int = 5, seat: str | None = None, variety: str | None = None):
    return load_archive_history(normalize_trade_date(trade_date), days=days, seat=seat, variety=variety)
