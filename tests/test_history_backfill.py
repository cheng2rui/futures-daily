from __future__ import annotations

from app.services.history_backfill import MAX_BACKFILL_DAYS, recent_weekdays


def check() -> None:
    assert recent_weekdays("20260112", 3) == ["20260108", "20260109", "20260112"]
    assert recent_weekdays("20260111", 1) == ["20260109"]
    assert len(recent_weekdays("20260130", MAX_BACKFILL_DAYS + 10)) == MAX_BACKFILL_DAYS


if __name__ == "__main__":
    check()
    print("ok")
