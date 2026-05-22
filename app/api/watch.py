from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SeatWatchlist, WatchSymbol
from app.metadata.variety_meta import get_exchange_code, get_variety_name
from app.services.structure import sector_for

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


class WatchBulkIn(BaseModel):
    text: str
    replace: bool = False


@router.get("/symbols")
def list_symbols(db: Session = Depends(get_db)):
    rows = db.scalars(select(WatchSymbol).order_by(WatchSymbol.sort_order, WatchSymbol.symbol)).all()
    return [symbol_out(r) for r in rows]


@router.post("/symbols/bulk")
def bulk_upsert_symbols(payload: WatchBulkIn, db: Session = Depends(get_db)):
    items = parse_watch_text(payload.text)
    if not items:
        raise HTTPException(status_code=400, detail="no valid symbols found")
    if payload.replace:
        for row in db.scalars(select(WatchSymbol)).all():
            db.delete(row)
        db.flush()
    existing = {(r.exchange or "", r.symbol or ""): r for r in db.scalars(select(WatchSymbol)).all()}
    changed = []
    for idx, item in enumerate(items):
        key = (item["exchange"], item["symbol"])
        row = existing.get(key)
        if row:
            row.name = item["name"] or row.name
            row.sector = item["sector"] or row.sector
            row.enabled = True
            row.sort_order = idx
            row.note = item["note"] or row.note
        else:
            row = WatchSymbol(**item, enabled=True, sort_order=idx)
            db.add(row)
            existing[key] = row
        changed.append(row)
    db.commit()
    for row in changed:
        db.refresh(row)
    return {"ok": True, "count": len(changed), "items": [symbol_out(r) for r in changed]}


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


def parse_watch_text(text: str) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    items = []
    for raw in re.split(r"[\n,，;；\s]+", text or ""):
        token = raw.strip().upper()
        if not token:
            continue
        match = re.match(r"^([A-Z]+)(\d{3,4})?$", token)
        if not match:
            continue
        variety = match.group(1)
        contract_suffix = match.group(2) or ""
        symbol = token if contract_suffix else variety
        exchange = get_exchange_code(variety, "")
        key = (exchange, symbol)
        if key in seen:
            continue
        seen.add(key)
        name = get_variety_name(variety)
        items.append({
            "symbol": symbol,
            "exchange": exchange,
            "name": name,
            "sector": sector_for(variety),
            "note": f"contract:{variety}{contract_suffix}" if contract_suffix else "",
        })
    return items


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
