"""Regression test: ensure collector never deletes existing data when fetch returns nothing."""

from __future__ import annotations

import os

# Must be set BEFORE importing app modules
os.environ["FUTURES_DAILY_DB"] = "data/futures_daily.db"

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DailyBar, SeatRankRow
from app.services.collector import collect_daily_market, collect_seat_ranks


def _make_result(rows=None, error=None):
    result = MagicMock()
    result.rows = rows or []
    result.error = error
    return result


def check() -> None:
    db = SessionLocal()
    trade_date = date.today().strftime("%Y%m%d")

    # ── DailyBar protection ──────────────────────────────────────────────────
    # Seed existing row so we can detect it is NOT deleted on a failed fetch
    db.execute(delete(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE"))
    db.add(DailyBar(trade_date=trade_date, exchange="SHFE", symbol="RB", contract="RB2509",
                    open=3700, high=3750, low=3690, close=3720,
                    pre_close=3710, volume=100000, open_interest=50000,
                    turnover=None, settlement=None, raw_json="{}"))
    db.commit()

    with patch("app.services.collector.get_market_provider") as mock_reg:
        mock_provider = MagicMock()
        mock_provider.fetch_daily.return_value = _make_result(rows=[], error="network timeout")
        mock_reg.return_value = mock_provider

        result = collect_daily_market(db, trade_date=trade_date, exchanges=["SHFE"])
        shfe_result = next(r for r in result["results"] if r["exchange"] == "SHFE")

    # Saved=0 means no delete+re-insert happened
    assert shfe_result["saved"] == 0, f"expected 0, got {shfe_result['saved']}"

    # The pre-existing row must still be there
    remaining = db.scalars(
        select(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE")
    ).all()
    assert len(remaining) == 1, f"expected existing row to survive, got {len(remaining)} rows"
    assert remaining[0].symbol == "RB"

    # When fetch returns actual rows, they replace old ones (no duplication)
    good_row = {
        "symbol": "RB", "contract": "RB2510",
        "open": 3700, "high": 3760, "low": 3695, "close": 3750,
        "pre_close": 3720, "volume": 110000, "open_interest": 52000,
        "turnover": None, "settlement": None,
        "raw": {"price": 3750},
    }
    with patch("app.services.collector.get_market_provider") as mock_reg:
        mock_provider = MagicMock()
        mock_provider.fetch_daily.return_value = _make_result(rows=[good_row])
        mock_reg.return_value = mock_provider

        result2 = collect_daily_market(db, trade_date=trade_date, exchanges=["SHFE"])
        shfe_result2 = next(r for r in result2["results"] if r["exchange"] == "SHFE")

    assert shfe_result2["saved"] == 1
    after = db.scalars(
        select(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE")
    ).all()
    assert len(after) == 1
    assert after[0].contract == "RB2510"

    # ── SeatRankRow protection ───────────────────────────────────────────────
    db.execute(delete(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE"))
    db.add(SeatRankRow(trade_date=trade_date, exchange="DCE", variety="M", contract="M2509",
                       rank=1, vol_party_name="永安", vol=5000, vol_chg=200,
                       long_party_name="", long_open_interest=None, long_open_interest_chg=None,
                       short_party_name="", short_open_interest=None, short_open_interest_chg=None,
                       raw_json="{}"))
    db.commit()

    with patch("app.services.collector.get_market_provider") as mock_reg:
        mock_provider = MagicMock()
        mock_provider.fetch_seat_rank.return_value = _make_result(rows=[], error="source unavailable")
        mock_reg.return_value = mock_provider

        result3 = collect_seat_ranks(db, trade_date=trade_date, exchanges=["DCE"])
        dce_result = next(r for r in result3["results"] if r["exchange"] == "DCE")

    assert dce_result["saved"] == 0
    existing_rank = db.scalars(
        select(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE")
    ).all()
    assert len(existing_rank) == 1
    assert existing_rank[0].vol_party_name == "永安"

    # Clean up
    db.execute(delete(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE"))
    db.execute(delete(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE"))
    db.commit()
    db.close()


if __name__ == "__main__":
    check()
    print("ok")