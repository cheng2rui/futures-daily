from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.report_builder import build_report
from app.services.trading_day import normalize_trade_date

MAX_BACKFILL_DAYS = 20


def recent_weekdays(end_date: str, days: int) -> list[str]:
    days = max(1, min(int(days or 1), MAX_BACKFILL_DAYS))
    d = datetime.strptime(normalize_trade_date(end_date), "%Y%m%d").date()
    out: list[str] = []
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return list(reversed(out))


def backfill_history(
    db: Session,
    *,
    end_date: str | None = None,
    days: int = 5,
    collect_daily: bool = True,
    collect_seats: bool = False,
    collect_enhancements: bool = True,
    rebuild_latest: bool = True,
) -> dict[str, Any]:
    """Backfill recent trading-day candidates for historical factors.

    Kept intentionally conservative: max 20 weekdays per request. Seat rank is
    opt-in because it is heavier and more fragile than daily bars/enhancements.
    """
    end = normalize_trade_date(end_date)
    dates = recent_weekdays(end, days)
    results: list[dict[str, Any]] = []
    for trade_date in dates:
        item: dict[str, Any] = {"trade_date": trade_date}
        if collect_daily:
            item["daily"] = collect_daily_market(db, trade_date)
        if collect_seats:
            item["seats"] = collect_seat_ranks(db, trade_date)
        if collect_enhancements:
            item["enhancements"] = collect_quhe_enhancements(db, trade_date)
        results.append(item)
    report = build_report(db, end) if rebuild_latest else None
    return {
        "ok": True,
        "end_date": end,
        "dates": dates,
        "days": len(dates),
        "results": results,
        "report": {"trade_date": report.trade_date, "score": report.score, "summary": report.summary} if report else None,
    }
