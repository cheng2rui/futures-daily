from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SeatWatchlist, WatchSymbol

router = APIRouter(prefix="/api/watch", tags=["watch"])


class WatchSymbolIn(BaseModel):
    symbol: str
    exchange: str = ""
    name: str = ""
    sector: str = ""
    enabled: bool = True
    sort_order: int = 0
    note: str = ""


class SeatWatchIn(BaseModel):
    seat_name: str
    alias: str = ""
    enabled: bool = True
    note: str = ""


@router.get("/symbols")
def list_symbols(db: Session = Depends(get_db)):
    rows = db.scalars(select(WatchSymbol).order_by(WatchSymbol.sort_order, WatchSymbol.symbol)).all()
    return [symbol_out(r) for r in rows]


@router.post("/symbols")
def create_symbol(payload: WatchSymbolIn, db: Session = Depends(get_db)):
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    row = WatchSymbol(
        symbol=symbol,
        exchange=payload.exchange.strip().upper(),
        name=payload.name.strip(),
        sector=payload.sector.strip(),
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        note=payload.note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return symbol_out(row)


@router.patch("/symbols/{item_id}")
def update_symbol(item_id: int, payload: WatchSymbolIn, db: Session = Depends(get_db)):
    row = db.get(WatchSymbol, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="watch symbol not found")
    row.symbol = payload.symbol.strip().upper()
    row.exchange = payload.exchange.strip().upper()
    row.name = payload.name.strip()
    row.sector = payload.sector.strip()
    row.enabled = payload.enabled
    row.sort_order = payload.sort_order
    row.note = payload.note
    db.commit()
    db.refresh(row)
    return symbol_out(row)


@router.delete("/symbols/{item_id}")
def delete_symbol(item_id: int, db: Session = Depends(get_db)):
    row = db.get(WatchSymbol, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="watch symbol not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/seats")
def list_seats(db: Session = Depends(get_db)):
    rows = db.scalars(select(SeatWatchlist).order_by(SeatWatchlist.seat_name)).all()
    return [seat_out(r) for r in rows]


@router.post("/seats")
def create_seat(payload: SeatWatchIn, db: Session = Depends(get_db)):
    seat_name = payload.seat_name.strip()
    if not seat_name:
        raise HTTPException(status_code=400, detail="seat_name required")
    row = SeatWatchlist(seat_name=seat_name, alias=payload.alias.strip(), enabled=payload.enabled, note=payload.note)
    db.add(row)
    db.commit()
    db.refresh(row)
    return seat_out(row)


@router.delete("/seats/{item_id}")
def delete_seat(item_id: int, db: Session = Depends(get_db)):
    row = db.get(SeatWatchlist, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="seat watch not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def symbol_out(r: WatchSymbol) -> dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "exchange": r.exchange,
        "name": r.name,
        "sector": r.sector,
        "enabled": r.enabled,
        "sort_order": r.sort_order,
        "note": r.note,
    }


def seat_out(r: SeatWatchlist) -> dict:
    return {"id": r.id, "seat_name": r.seat_name, "alias": r.alias, "enabled": r.enabled, "note": r.note}
