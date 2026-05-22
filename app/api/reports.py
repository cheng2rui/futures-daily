from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import JobRun, Report
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.data_quality import build_data_quality
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.report_builder import build_report
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).order_by(desc(Report.trade_date)).limit(limit)).all()
    return [
        {
            "trade_date": r.trade_date,
            "status": r.status,
            "score": r.score,
            "summary": r.summary,
            "generated_at": r.generated_at,
        }
        for r in rows
    ]


@router.get("/latest")
def latest_report(db: Session = Depends(get_db)):
    report = db.scalar(select(Report).order_by(desc(Report.trade_date)).limit(1))
    if not report:
        return empty_report()
    return json.loads(report.report_json)


@router.get("/{trade_date}")
def get_report(trade_date: str, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return json.loads(report.report_json)


@router.post("/generate")
def generate_report(trade_date: str | None = None, collect: bool = True, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    collect_result = None
    seat_result = None
    job = JobRun(name="generate_report", status="running", trade_date=trade_date, started_at=datetime.utcnow())
    db.add(job)
    db.commit()
    try:
        quhe_result = None
        if collect:
            collect_result = collect_daily_market(db, trade_date)
            seat_result = collect_seat_ranks(db, trade_date)
            quhe_result = collect_quhe_enhancements(db, trade_date)
        report = build_report(db, trade_date)
        job.status = "success"
        job.message = report.summary
        job.result_json = json.dumps({"collect": collect_result, "seats": seat_result, "quhe": quhe_result}, ensure_ascii=False, default=str)
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.utcnow()
        db.commit()
        raise
    return {
        "ok": True,
        "trade_date": trade_date,
        "score": report.score,
        "summary": report.summary,
        "collect": collect_result,
        "seats": seat_result,
        "quhe": quhe_result,
        "data_quality": build_data_quality(db, trade_date),
    }


def empty_report():
    return {
        "date": None,
        "meta": {"generated_at": None, "version": "0.1.0"},
        "overview": {"score": 0, "stage": "暂无数据", "heat": 0, "risk": 0, "summary": "暂无日报，请先生成。"},
        "market": {"up_count": 0, "down_count": 0, "turnover": 0, "volume": 0, "contracts": 0},
        "sectors": [],
        "rankings": {"gainers": [], "losers": [], "volume": [], "open_interest": []},
        "seats": {"long_increase_top": [], "short_increase_top": [], "watchlist": []},
        "watch_symbols": [],
        "data_quality": {"status": "empty", "daily_ok": 0, "expected": 6, "coverage_pct": 0, "exchanges": []},
        "risk_flags": [],
        "action_notes": [],
    }
