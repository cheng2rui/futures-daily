from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Report
from app.services.assistant.service import analyze_seats, assistant_status, summarize_report
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/status")
def status():
    return assistant_status()


@router.post("/summarize-report")
async def summarize(trade_date: str | None = None, db: Session = Depends(get_db)):
    report = _load_report(db, trade_date)
    result = await summarize_report(report)
    return result.__dict__


@router.post("/analyze-seat")
async def seat_analysis(trade_date: str | None = None, db: Session = Depends(get_db)):
    report = _load_report(db, trade_date)
    result = await analyze_seats(report)
    return result.__dict__


def _load_report(db: Session, trade_date: str | None) -> dict:
    if trade_date:
        td = normalize_trade_date(trade_date)
        row = db.scalar(select(Report).where(Report.trade_date == td))
    else:
        row = db.scalar(select(Report).order_by(desc(Report.trade_date)).limit(1))
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    return json.loads(row.report_json)
