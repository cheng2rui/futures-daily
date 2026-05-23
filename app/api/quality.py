from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_quality import build_data_quality
from app.services.source_diagnostics import diagnose_weak_sources
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/coverage/{trade_date}")
def get_coverage_matrix(trade_date: str, sync_gaps: bool = True, db: Session = Depends(get_db)):
    return build_coverage_matrix(db, normalize_trade_date(trade_date), sync_gaps=sync_gaps)


@router.get("/diagnostics/{trade_date}")
def get_source_diagnostics(trade_date: str, exchange: str | None = None, db: Session = Depends(get_db)):
    exchanges = [exchange] if exchange else None
    return diagnose_weak_sources(db, normalize_trade_date(trade_date), exchanges=exchanges)


@router.get("/{trade_date}")
def get_quality(trade_date: str, db: Session = Depends(get_db)):
    quality = build_data_quality(db, normalize_trade_date(trade_date))
    quality["coverage_matrix"] = build_coverage_matrix(db, normalize_trade_date(trade_date), sync_gaps=False)
    return quality
