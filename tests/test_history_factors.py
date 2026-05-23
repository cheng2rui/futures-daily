from __future__ import annotations

from app.models import DailyBar
from app.services.history_factors import build_history_context, percentile_rank


def check() -> None:
    assert percentile_rank(3, [1, 2, 3, 4, 5]) == 50
    assert percentile_rank(5, [1, 2, 3, 4, 5]) == 90

    class DB:
        def scalars(self, stmt):
            return iter(make_bars())

    ctx = build_history_context(DB(), "20260108", windows=(5,))
    rb = ctx["RB"]
    assert rb["status"] == "ok"
    assert rb["highlights"]
    volume = next(x for x in rb["metrics"] if x["key"] == "volume")
    assert volume["percentile"] >= 90
    assert "高位" in rb["summary"]


def make_bars() -> list[DailyBar]:
    out = []
    closes = [100, 101, 102, 103, 104, 105, 106, 112]
    volumes = [1000, 1100, 1200, 1300, 1400, 1500, 1600, 5000]
    for idx, (close, volume) in enumerate(zip(closes, volumes), 1):
        out.append(
            DailyBar(
                trade_date=f"202601{idx:02d}",
                exchange="SHFE",
                symbol="RB",
                contract="RB2605",
                close=close,
                pre_close=closes[idx - 2] if idx > 1 else close - 1,
                volume=volume,
                open_interest=10000 + idx * 100,
            )
        )
    return out


if __name__ == "__main__":
    check()
    print("ok")
