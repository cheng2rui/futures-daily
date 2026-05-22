from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DailyBar, WatchSymbol

router = APIRouter(prefix="/api/markets", tags=["markets"])


@router.get("/bars")
def list_bars(trade_date: str | None = None, symbol: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    stmt = select(DailyBar).order_by(desc(DailyBar.trade_date), DailyBar.exchange, DailyBar.contract).limit(limit)
    if trade_date:
        stmt = stmt.where(DailyBar.trade_date == trade_date)
    if symbol:
        stmt = stmt.where(DailyBar.symbol == symbol.upper())
    rows = db.scalars(stmt).all()
    return [
        {
            "trade_date": r.trade_date,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "contract": r.contract,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "open_interest": r.open_interest,
            "turnover": r.turnover,
        }
        for r in rows
    ]


@router.get("/watch-symbols")
def list_watch_symbols(db: Session = Depends(get_db)):
    rows = db.scalars(select(WatchSymbol).order_by(WatchSymbol.sort_order, WatchSymbol.symbol)).all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "exchange": r.exchange,
            "name": r.name,
            "sector": r.sector,
            "enabled": r.enabled,
            "sort_order": r.sort_order,
            "note": r.note,
        }
        for r in rows
    ]
