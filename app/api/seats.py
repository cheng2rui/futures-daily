from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SeatRankRow, SeatWatchlist

router = APIRouter(prefix="/api/seats", tags=["seats"])


@router.get("/rank-rows")
def list_seat_rows(
    trade_date: str | None = None,
    variety: str | None = None,
    seat: str | None = None,
    exchange: str | None = None,
    limit: int = 300,
    db: Session = Depends(get_db),
):
    stmt = select(SeatRankRow).order_by(desc(SeatRankRow.trade_date), SeatRankRow.exchange, SeatRankRow.variety, SeatRankRow.rank).limit(limit)
    if trade_date:
        stmt = stmt.where(SeatRankRow.trade_date == trade_date)
    if variety:
        stmt = stmt.where(SeatRankRow.variety == variety.upper())
    if exchange:
        stmt = stmt.where(SeatRankRow.exchange == exchange.upper())
    if seat:
        like = f"%{seat}%"
        stmt = stmt.where(
            (SeatRankRow.long_party_name.like(like)) |
            (SeatRankRow.short_party_name.like(like)) |
            (SeatRankRow.vol_party_name.like(like))
        )
    rows = db.scalars(stmt).all()
    return [
        {
            "trade_date": r.trade_date,
            "exchange": r.exchange,
            "variety": r.variety,
            "contract": r.contract,
            "rank": r.rank,
            "vol_party_name": r.vol_party_name,
            "vol": r.vol,
            "vol_chg": r.vol_chg,
            "long_party_name": r.long_party_name,
            "long_open_interest": r.long_open_interest,
            "long_open_interest_chg": r.long_open_interest_chg,
            "short_party_name": r.short_party_name,
            "short_open_interest": r.short_open_interest,
            "short_open_interest_chg": r.short_open_interest_chg,
        }
        for r in rows
    ]


@router.get("/watchlist")
def list_seat_watchlist(db: Session = Depends(get_db)):
    rows = db.scalars(select(SeatWatchlist).order_by(SeatWatchlist.seat_name)).all()
    return [{"id": r.id, "seat_name": r.seat_name, "alias": r.alias, "enabled": r.enabled, "note": r.note} for r in rows]
