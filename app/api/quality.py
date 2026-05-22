from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.data_quality import build_data_quality
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/{trade_date}")
def get_quality(trade_date: str, db: Session = Depends(get_db)):
    return build_data_quality(db, normalize_trade_date(trade_date))
