from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.report_builder import build_report

_scheduler: BackgroundScheduler | None = None


def generate_daily_report_job() -> None:
    db = SessionLocal()
    try:
        market = collect_daily_market(db)
        seats = collect_seat_ranks(db, market["trade_date"])
        build_report(db, market["trade_date"])
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
