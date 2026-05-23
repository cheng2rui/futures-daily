from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CrawlerRun, DailyBar, DailyCoverage, DataGap, SourceFile, VarietyDailyFact
from app.services.data_mart import build_variety_dataset, materialize_variety_dataset
from app.services.gap_analysis import build_gap_analysis
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.raw_archive import list_archives, read_archive, source_file_item
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.get("/varieties/latest")
def get_latest_variety_dataset(db: Session = Depends(get_db)):
    latest = db.scalar(select(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))
    trade_date = normalize_trade_date(latest) if latest else normalize_trade_date(None)
    return build_variety_dataset(db, trade_date)


@router.get("/varieties/{trade_date}")
def get_variety_dataset(trade_date: str, db: Session = Depends(get_db)):
    return build_variety_dataset(db, normalize_trade_date(trade_date))


@router.post("/materialize/{trade_date}")
def materialize_dataset(trade_date: str, db: Session = Depends(get_db)):
    return materialize_variety_dataset(db, normalize_trade_date(trade_date))


@router.post("/collect-quhe/{trade_date}")
def collect_quhe_dataset(trade_date: str, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    result = collect_quhe_enhancements(db, trade_date)
    materialized = materialize_variety_dataset(db, trade_date)
    return {"collect": result, "materialized": materialized}


@router.get("/facts/{trade_date}")
def list_variety_facts(trade_date: str, limit: int = 300, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(VarietyDailyFact)
        .where(VarietyDailyFact.trade_date == normalize_trade_date(trade_date))
        .order_by(VarietyDailyFact.exchange, VarietyDailyFact.symbol)
        .limit(limit)
    ).all()
    return [fact_item(r) for r in rows]


@router.get("/coverage/{trade_date}")
def list_daily_coverage(trade_date: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DailyCoverage)
        .where(DailyCoverage.trade_date == normalize_trade_date(trade_date))
        .order_by(DailyCoverage.exchange)
    ).all()
    return [coverage_item(r) for r in rows]


@router.get("/crawler-runs")
def list_crawler_runs(trade_date: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(CrawlerRun).order_by(desc(CrawlerRun.started_at)).limit(limit)
    if trade_date:
        stmt = stmt.where(CrawlerRun.trade_date == normalize_trade_date(trade_date))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "trade_date": r.trade_date,
            "exchange": r.exchange,
            "kind": r.kind,
            "source": r.source,
            "status": r.status,
            "rows": r.rows,
            "saved": r.saved,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in rows
    ]


@router.get("/gap-analysis/{trade_date}")
def get_gap_analysis(trade_date: str, db: Session = Depends(get_db)):
    return build_gap_analysis(db, normalize_trade_date(trade_date))


@router.get("/raw-archives")
def list_raw_archives(trade_date: str | None = None, exchange: str | None = None, kind: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    date_filter = normalize_trade_date(trade_date) if trade_date else None
    return [source_file_item(r) for r in list_archives(db, trade_date=date_filter, exchange=exchange, kind=kind, limit=limit)]


@router.get("/raw-archives/{file_id}")
def get_raw_archive(file_id: int, db: Session = Depends(get_db)):
    row = db.scalar(select(SourceFile).where(SourceFile.id == file_id))
    if not row:
        return {"error": "not_found"}
    return read_archive(row)


@router.get("/gaps")
def list_data_gaps(trade_date: str | None = None, status: str | None = "open", db: Session = Depends(get_db)):
    stmt = select(DataGap).order_by(desc(DataGap.trade_date), DataGap.exchange, DataGap.kind)
    if trade_date:
        stmt = stmt.where(DataGap.trade_date == normalize_trade_date(trade_date))
    if status:
        stmt = stmt.where(DataGap.status == status)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "trade_date": r.trade_date,
            "exchange": r.exchange,
            "kind": r.kind,
            "severity": r.severity,
            "status": r.status,
            "rows": r.rows,
            "message": r.message,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r in rows
    ]


def fact_item(r: VarietyDailyFact) -> dict:
    parsed = parse_fact_json(r)
    return {
        "id": r.id,
        "trade_date": r.trade_date,
        "exchange": r.exchange,
        "symbol": r.symbol,
        "name": r.name,
        "sector": r.sector,
        "contracts": r.contracts,
        "main_contract": r.main_contract,
        "main_close": r.main_close,
        "main_change_pct": r.main_change_pct,
        "total_volume": r.total_volume,
        "total_open_interest": r.total_open_interest,
        "notional_oi": r.notional_oi,
        "seat_rank_rows": r.seat_rank_rows,
        "seat_net_delta_top20": r.seat_net_delta_top20,
        "archive_net_delta": r.archive_net_delta,
        "archive_long_short_ratio": r.archive_long_short_ratio,
        "archive_long_cr5": r.archive_long_cr5,
        "archive_short_cr5": r.archive_short_cr5,
        "quality_daily": r.quality_daily,
        "quality_seat_rank": r.quality_seat_rank,
        "quality_archive_signal": r.quality_archive_signal,
        "external_signals": parsed.get("external_signals", {}),
        "updated_at": r.updated_at,
    }


def parse_fact_json(r: VarietyDailyFact) -> dict:
    try:
        return json.loads(r.fact_json or "{}")
    except Exception:
        return {}


def coverage_item(r: DailyCoverage) -> dict:
    return {
        "id": r.id,
        "trade_date": r.trade_date,
        "exchange": r.exchange,
        "varieties": r.varieties,
        "with_seat_rank": r.with_seat_rank,
        "with_archive_signal": r.with_archive_signal,
        "daily_status": r.daily_status,
        "seat_status": r.seat_status,
        "archive_status": r.archive_status,
        "message": r.message,
        "updated_at": r.updated_at,
    }
