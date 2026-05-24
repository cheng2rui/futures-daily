from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import JobRun, Report
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.coverage_diff import diff_coverage_matrix
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_quality import build_data_quality
from app.services.news_collector import collect_news_digest
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.notify import NotifyEvent, dispatch
from app.services.push_digest import build_push_digest
from app.services.report_builder import REPORT_SCHEMA_VERSION, build_report
from app.services.trading_day import normalize_trade_date

from app.version import VERSION

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
    return ensure_report_payload(db, report)




@router.get("/latest/push-digest")
def latest_push_digest(db: Session = Depends(get_db)):
    report = db.scalar(select(Report).order_by(desc(Report.trade_date)).limit(1))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    payload = ensure_report_payload(db, report)
    return payload.get("push_digest") or build_push_digest(payload)


@router.get("/{trade_date}/push-digest")
def get_push_digest(trade_date: str, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    payload = ensure_report_payload(db, report)
    return payload.get("push_digest") or build_push_digest(payload)


@router.get("/{trade_date}")
def get_report(trade_date: str, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return ensure_report_payload(db, report)


@router.post("/latest/push")
async def push_latest_report(db: Session = Depends(get_db)):
    report = db.scalar(select(Report).order_by(desc(Report.trade_date)).limit(1))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return await _dispatch_report_push(db, ensure_report_payload(db, report), source="manual_latest")


@router.post("/{trade_date}/push")
async def push_report(trade_date: str, db: Session = Depends(get_db)):
    trade_date = normalize_trade_date(trade_date)
    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return await _dispatch_report_push(db, ensure_report_payload(db, report), source="manual_date")


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
        news_result = None
        if collect:
            collect_result = collect_daily_market(db, trade_date)
            seat_result = collect_seat_ranks(db, trade_date)
            quhe_result = collect_quhe_enhancements(db, trade_date)
            news_result = collect_news_digest(db, trade_date)
        report = build_report(db, trade_date)
        job.status = "success"
        job.message = report.summary
        job.result_json = json.dumps({"collect": collect_result, "seats": seat_result, "quhe": quhe_result, "news": news_result}, ensure_ascii=False, default=str)
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
        "news": news_result,
        "data_quality": build_data_quality(db, trade_date),
    }


@router.post("/{trade_date}/recollect")
def recollect_report_data(
    trade_date: str,
    exchange: str | None = None,
    kinds: list[str] = Query(default=["daily", "seat_rank"]),
    rebuild: bool = True,
    db: Session = Depends(get_db),
):
    trade_date = normalize_trade_date(trade_date)
    selected_exchange = exchange.upper() if exchange else None
    enabled_exchanges = [str(x).upper() for x in get_settings().exchanges.enabled]
    if selected_exchange and selected_exchange not in enabled_exchanges:
        raise HTTPException(status_code=400, detail=f"unsupported exchange: {selected_exchange}")
    normalized_kinds = {str(k).lower() for k in kinds}
    if "all" in normalized_kinds:
        normalized_kinds = {"daily", "seat_rank"}
    unsupported = normalized_kinds - {"daily", "seat_rank"}
    if unsupported:
        raise HTTPException(status_code=400, detail=f"unsupported kinds: {', '.join(sorted(unsupported))}")

    job = JobRun(
        name="recollect_report",
        status="running",
        trade_date=trade_date,
        started_at=datetime.utcnow(),
        message=f"exchange={selected_exchange or 'ALL'} kinds={','.join(sorted(normalized_kinds))}",
    )
    db.add(job)
    db.commit()
    try:
        before_quality = build_data_quality(db, trade_date)
        before_matrix = build_coverage_matrix(db, trade_date, sync_gaps=False)
        exchanges = [selected_exchange] if selected_exchange else None
        collect_result = collect_daily_market(db, trade_date, exchanges=exchanges) if "daily" in normalized_kinds else None
        seat_result = collect_seat_ranks(db, trade_date, exchanges=exchanges) if "seat_rank" in normalized_kinds else None
        report = build_report(db, trade_date) if rebuild else None
        quality = build_data_quality(db, trade_date)
        after_matrix = build_coverage_matrix(db, trade_date, sync_gaps=False)
        coverage_diff = diff_coverage_matrix(before_matrix, after_matrix)
        summary = _recollect_summary(selected_exchange or "ALL", normalized_kinds, collect_result, seat_result, before_quality, quality, coverage_diff)
        job.status = "success" if quality.get("status") == "ok" else "partial"
        job.message = summary
        job.result_json = json.dumps(
            {
                "exchange": selected_exchange or "ALL",
                "kinds": sorted(normalized_kinds),
                "collect": collect_result,
                "seats": seat_result,
                "rebuild": bool(rebuild),
                "before_quality": before_quality,
                "quality": quality,
                "before_coverage_matrix": before_matrix,
                "after_coverage_matrix": after_matrix,
                "coverage_diff": coverage_diff,
                "summary": summary,
            },
            ensure_ascii=False,
            default=str,
        )
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
        "exchange": selected_exchange or "ALL",
        "kinds": sorted(normalized_kinds),
        "collect": collect_result,
        "seats": seat_result,
        "data_quality": quality,
        "coverage_diff": coverage_diff,
        "summary": summary,
        "report": {"score": report.score, "summary": report.summary} if report else None,
        "job_id": job.id,
        "job_status": job.status,
    }


def _recollect_summary(exchange: str, kinds: set[str], collect_result: dict | None, seat_result: dict | None, before_quality: dict, after_quality: dict, coverage_diff: dict | None = None) -> str:
    parts = [f"{exchange} 补采完成"]
    if "daily" in kinds and collect_result:
        saved = sum(int(x.get("saved") or 0) for x in collect_result.get("results", []))
        failed = [x for x in collect_result.get("results", []) if x.get("error")]
        parts.append(f"行情保存 {saved} 行" + (f"，异常 {len(failed)} 个" if failed else ""))
    if "seat_rank" in kinds and seat_result:
        saved = sum(int(x.get("saved") or 0) for x in seat_result.get("results", []))
        failed = [x for x in seat_result.get("results", []) if x.get("error")]
        parts.append(f"席位保存 {saved} 行" + (f"，异常 {len(failed)} 个" if failed else ""))
    before = before_quality.get("overall_coverage_pct") or before_quality.get("coverage_pct") or 0
    after = after_quality.get("overall_coverage_pct") or after_quality.get("coverage_pct") or 0
    if before != after:
        parts.append(f"可信度 {before}% → {after}%")
    else:
        parts.append(f"可信度 {after}%")
    if coverage_diff and coverage_diff.get("changed_cells"):
        parts.append(coverage_diff.get("summary") or f"覆盖变化 {coverage_diff.get('changed_cells')} 项")
    return "；".join(parts)


async def _dispatch_report_push(db: Session, payload: dict[str, Any], source: str) -> dict:
    digest = payload.get("push_digest") or build_push_digest(payload)
    trade_date = payload.get("date") or ""
    job = JobRun(name="push_report", status="running", trade_date=trade_date, started_at=datetime.utcnow(), message=f"dispatch {source}")
    db.add(job)
    db.commit()
    try:
        results = await dispatch(NotifyEvent(type="daily_report", title=digest["title"], message=digest["brief"], payload={"trade_date": trade_date, "source": source}))
        failed = [x for x in results if x.get("ok") is False]
        sent = [x for x in results if x.get("ok") is True]
        skipped = [x for x in results if x.get("skipped")]
        job.status = "failed" if failed and not sent else "partial" if failed or skipped else "success"
        job.message = f"sent={len(sent)} skipped={len(skipped)} failed={len(failed)}"
        job.result_json = json.dumps(
            {
                "dispatch": results,
                "digest_title": digest.get("title"),
                "digest_brief": digest.get("brief"),
                "digest_text": digest.get("text"),
                "source": source,
            },
            ensure_ascii=False,
            default=str,
        )
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.utcnow()
        db.commit()
        raise
    return {"ok": True, "trade_date": trade_date, "digest": digest, "dispatch": results, "job_id": job.id, "job_status": job.status}


def ensure_report_payload(db: Session, report: Report) -> dict:
    try:
        payload = json.loads(report.report_json or "{}")
    except Exception:
        payload = {}
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    schema_version = int((meta or {}).get("report_schema_version") or 0)
    if schema_version < REPORT_SCHEMA_VERSION or not payload.get("report_sections") or not payload.get("report_brief"):
        report = build_report(db, report.trade_date)
        payload = json.loads(report.report_json or "{}")
    return payload


def empty_report():
    return {
        "date": None,
        "meta": {"generated_at": None, "version": VERSION, "report_schema_version": REPORT_SCHEMA_VERSION},
        "overview": {"score": 0, "stage": "暂无数据", "heat": "暂无热度", "risk": 0, "direction": "暂无方向", "temperature": {"details": []}, "summary": "暂无日报，请先生成。"},
        "market": {"up_count": 0, "down_count": 0, "turnover": 0, "volume": 0, "contracts": 0},
        "sectors": [],
        "rankings": {"gainers": [], "losers": [], "volume": [], "open_interest": []},
        "seats": {"long_increase_top": [], "short_increase_top": [], "watchlist": []},
        "watch_symbols": [],
        "data_quality": {"status": "empty", "daily_ok": 0, "expected": 6, "coverage_pct": 0, "exchanges": []},
        "risk_flags": [],
        "action_notes": [],
    }
