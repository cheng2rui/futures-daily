from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import json

from app.db import get_db
from app.models import JobRun
from app.services.history_backfill import MAX_BACKFILL_DAYS, backfill_history, recent_weekdays
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/backfill-plan")
def backfill_plan(end_date: str | None = None, days: int = Query(default=5, ge=1, le=MAX_BACKFILL_DAYS)):
    end = normalize_trade_date(end_date)
    return {"end_date": end, "days": days, "dates": recent_weekdays(end, days), "max_days": MAX_BACKFILL_DAYS}


@router.post("/backfill")
def run_backfill(
    end_date: str | None = None,
    days: int = Query(default=5, ge=1, le=MAX_BACKFILL_DAYS),
    seats: bool = False,
    enhancements: bool = True,
    rebuild_latest: bool = True,
    db: Session = Depends(get_db),
):
    end = normalize_trade_date(end_date)
    job = JobRun(name="history_backfill", status="running", trade_date=end, started_at=datetime.utcnow(), message=f"days={days} seats={seats} enhancements={enhancements}")
    db.add(job)
    db.commit()
    try:
        result = backfill_history(
            db,
            end_date=end,
            days=days,
            collect_daily=True,
            collect_seats=seats,
            collect_enhancements=enhancements,
            rebuild_latest=rebuild_latest,
        )
        failed = summarize_failed(result)
        job.status = "partial" if failed else "success"
        job.message = f"补采 {result.get('days', 0)} 个交易日" + (f"，异常 {len(failed)} 项" if failed else "")
        job.result_json = json.dumps({**result, "failed": failed}, ensure_ascii=False, default=str)
        job.finished_at = datetime.utcnow()
        db.commit()
        result["job_id"] = job.id
        result["job_status"] = job.status
        result["failed"] = failed
        return result
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.utcnow()
        db.commit()
        raise


def summarize_failed(result: dict) -> list[dict]:
    failed: list[dict] = []
    for day in result.get("results", []) or []:
        trade_date = day.get("trade_date")
        for group in ["daily", "seats"]:
            for item in ((day.get(group) or {}).get("results") or []):
                if item.get("error") or int(item.get("saved") or 0) <= 0:
                    failed.append({"trade_date": trade_date, "kind": group, "exchange": item.get("exchange"), "error": item.get("error") or "empty"})
        enh = day.get("enhancements") or {}
        for group, payload in enh.items():
            if isinstance(payload, dict) and payload.get("error"):
                failed.append({"trade_date": trade_date, "kind": group, "error": payload.get("error")})
    return failed[:50]
