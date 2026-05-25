from __future__ import annotations

import sys
from types import SimpleNamespace

from app.sources import akshare_source
from app.sources.akshare_source import AkShareSource


class EmptyDceAk:
    def get_dce_daily(self, date: str):
        return SimpleNamespace(empty=True)


class EmptyDceRankAk:
    def get_dce_rank_table(self, date: str):
        return {}


def check() -> None:
    old_ak = sys.modules.get("akshare")
    old_daily_fallback = akshare_source.fetch_dce_daily_from_sina
    old_seat_fallback = akshare_source.fetch_dce_seat_rank_from_sina
    try:
        sys.modules["akshare"] = EmptyDceAk()
        akshare_source.fetch_dce_daily_from_sina = lambda trade_date: SimpleNamespace(rows=[{"symbol": "M", "contract": "M0"}], error=None)
        result = AkShareSource().fetch_daily("20260522", "DCE")
        assert result.rows == [{"symbol": "M", "contract": "M0"}]
        assert result.error == "DCE official returned empty; used Sina fallback"

        akshare_source.fetch_dce_daily_from_sina = lambda trade_date: SimpleNamespace(rows=[], error=None)
        result = AkShareSource().fetch_daily("20260522", "DCE")
        assert result.rows == []
        assert result.error == "DCE official returned empty; Sina fallback unavailable"

        sys.modules["akshare"] = EmptyDceRankAk()
        akshare_source.fetch_dce_seat_rank_from_sina = lambda trade_date: SimpleNamespace(rows=[{"variety": "M"}], error="fallback partial")
        result = AkShareSource().fetch_seat_rank("20260522", "DCE")
        assert result.rows == [{"variety": "M"}]
        assert result.error == "fallback partial"
    finally:
        akshare_source.fetch_dce_daily_from_sina = old_daily_fallback
        akshare_source.fetch_dce_seat_rank_from_sina = old_seat_fallback
        if old_ak is None:
            sys.modules.pop("akshare", None)
        else:
            sys.modules["akshare"] = old_ak


if __name__ == "__main__":
    check()
    print("ok")
