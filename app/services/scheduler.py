from __future__ import annotations

import asyncio
import json
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.models import JobRun
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.news_collector import collect_news_digest
from app.services.notify import NotifyEvent, dispatch
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.report_builder import build_report

_scheduler: BackgroundScheduler | None = None


def generate_daily_report_job() -> None:
    db = SessionLocal()
    try:
        market = collect_daily_market(db)
        seats = collect_seat_ranks(db, market["trade_date"])
        collect_quhe_enhancements(db, market["trade_date"])
        collect_news_digest(db, market["trade_date"])
        report = build_report(db, market["trade_date"])
        try:
            payload = json.loads(report.report_json or "{}")
            digest = payload.get("push_digest") or {}
            if digest.get("brief"):
                push_job = JobRun(name="push_report", status="running", trade_date=market["trade_date"], message="dispatch scheduled")
                db.add(push_job)
                db.commit()
                try:
                    results = asyncio.run(dispatch(NotifyEvent(type="daily_report", title=digest.get("title") or "期货日报", message=digest["brief"], payload={"trade_date": market["trade_date"], "source": "scheduled"})))
                    failed = [x for x in results if x.get("ok") is False]
                    sent = [x for x in results if x.get("ok") is True]
                    skipped = [x for x in results if x.get("skipped")]
                    push_job.status = "failed" if failed and not sent else "partial" if failed or skipped else "success"
                    push_job.message = f"sent={len(sent)} skipped={len(skipped)} failed={len(failed)}"
                    push_job.result_json = json.dumps({"dispatch": results, "source": "scheduled"}, ensure_ascii=False, default=str)
                    push_job.finished_at = datetime.utcnow()
                    db.commit()
                except Exception as exc:  # noqa: BLE001
                    push_job.status = "failed"
                    push_job.message = f"{type(exc).__name__}: {exc}"
                    push_job.finished_at = datetime.utcnow()
                    db.commit()
        except Exception:
            # Notification failure must not fail scheduled report generation.
            pass
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings().scheduler
    if not settings.enabled or _scheduler:
        return
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    minute, hour, day, month, dow = settings.daily_report_cron.split()
    scheduler.add_job(generate_daily_report_job, "cron", minute=minute, hour=hour, day=day, month=month, day_of_week=dow, id="daily_report", replace_existing=True)
    scheduler.start()
    _scheduler = scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
