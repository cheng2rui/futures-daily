from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import CrawlerRun, DailyBar, DataGap, JobRun, Report, SourceFile
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.coverage_diff import diff_coverage_matrix
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_quality import build_data_quality
from app.services.news_collector import collect_news_digest
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.notify import NotifyEvent, dispatch
from app.services.push_digest import build_push_digest
from app.services.report_builder import REPORT_SCHEMA_VERSION, build_report
from app.services.run_records import complete_state_from_coverage, coverage_counts, run_summary
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
    return annotate_latest_state(db, ensure_report_payload(db, report), report)




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
        coverage_matrix = build_coverage_matrix(db, trade_date, sync_gaps=False)
        summary_record = run_summary(
            run_id=f"generate_report:{job.id}",
            trade_date=trade_date,
            profile="generate_report",
            status=complete_state_from_coverage(coverage_matrix, report.status),
            counts=coverage_counts(coverage_matrix),
            error=report.summary if report.status == "blocked" else "",
            started_at=job.started_at,
        )
        job.status = "partial" if report.status == "blocked" else "success"
        job.message = report.summary
        job.result_json = json.dumps({"collect": collect_result, "seats": seat_result, "quhe": quhe_result, "news": news_result, "run_summary": summary_record}, ensure_ascii=False, default=str)
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


def _safe_schema_version(meta: Any) -> int:
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("report_schema_version") or 0)
    except (TypeError, ValueError):
        return 0


def ensure_report_payload(db: Session, report: Report) -> dict:
    try:
        payload = json.loads(report.report_json or "{}")
    except Exception:
        payload = {}
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    schema_version = _safe_schema_version(meta)
    if schema_version < REPORT_SCHEMA_VERSION or not payload.get("report_sections") or not payload.get("report_brief"):
        report = build_report(db, report.trade_date)
        payload = json.loads(report.report_json or "{}")
    return payload


def annotate_latest_state(db: Session, payload: dict[str, Any], report: Report) -> dict[str, Any]:
    """Make stale latest-report states explicit instead of silently showing an older day.

    A failed collection day can create crawler runs/gaps/source files without a
    report. The UI still asks for /reports/latest, so attach a small operational
    state block whenever the latest pipeline activity is newer than the latest
    report.
    """
    latest_activity = latest_pipeline_activity_date(db)
    state = {
        "status": "current",
        "report_date": report.trade_date,
        "latest_activity_date": latest_activity or report.trade_date,
        "message": "当前展示的是最新已生成日报。",
    }
    if latest_activity and latest_activity > report.trade_date:
        state = {
            "status": "stale",
            "report_date": report.trade_date,
            "latest_activity_date": latest_activity,
            "message": f"最新采集/诊断活动在 {latest_activity}，但尚未形成有效日报；当前仍展示 {report.trade_date}。",
            "next_action": "先查看数据诊断或执行自动补采，再重新生成日报。",
        }
    payload.setdefault("meta", {})["latest_state"] = state
    current_state = latest_complete_run_state(db, report.trade_date, payload)
    if current_state:
        payload["meta"]["current_state"] = current_state
    return payload


def latest_complete_run_state(db: Session, trade_date: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = db.scalars(
        select(JobRun)
        .where(JobRun.trade_date == trade_date)
        .order_by(desc(JobRun.started_at))
        .limit(20)
    ).all()
    for row in rows:
        data = parse_json(row.result_json)
        run_summary = data.get("run_summary") if isinstance(data.get("run_summary"), dict) else None
        if not run_summary:
            continue
        status = str(run_summary.get("status") or "")
        if status not in {"complete", "partial", "error"}:
            continue
        return {
            "status": status,
            "run_id": run_summary.get("run_id") or row.id,
            "profile": run_summary.get("profile") or row.name,
            "trade_date": trade_date,
            "message": {
                "complete": "当前日报由完整 run 提升而来。",
                "partial": "当前日报来自部分完成的 run，仍需留意缺口。",
                "error": "当前日报尚未形成可用 current-state。",
            }.get(status, ""),
            "counts": run_summary.get("counts") or {},
            "end_time": run_summary.get("end_time") or (row.finished_at.isoformat() if row.finished_at else None),
        }
    return None


def latest_pipeline_activity_date(db: Session) -> str | None:
    candidates = [
        db.scalar(select(func.max(DailyBar.trade_date))),
        db.scalar(select(func.max(CrawlerRun.trade_date))),
        db.scalar(select(func.max(DataGap.trade_date))),
        db.scalar(select(func.max(SourceFile.trade_date))),
    ]
    values = [str(x) for x in candidates if x]
    return max(values) if values else None


def parse_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


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
