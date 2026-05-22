from __future__ import annotations

from datetime import date, datetime, timedelta


def normalize_trade_date(value: str | None = None) -> str:
    if not value:
        return latest_candidate_trade_date()
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    if len(digits) != 8:
        raise ValueError('trade_date must be YYYYMMDD or YYYY-MM-DD')
    return digits


def latest_candidate_trade_date(now: datetime | None = None) -> str:
    """Return latest weekday candidate.

    This is intentionally simple for MVP. A real exchange calendar can replace it later.
    After weekends, falls back to Friday. Holidays will be handled by source failures/data quality.
    """
    d = (now or datetime.now()).date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y%m%d')
