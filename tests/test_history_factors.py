from __future__ import annotations

from app.models import BasisDaily, DailyBar, VarietyDailyFact, WarehouseReceiptDaily
from app.services.history_factors import build_history_context, percentile_rank


def check() -> None:
    assert percentile_rank(3, [1, 2, 3, 4, 5]) == 50
    assert percentile_rank(5, [1, 2, 3, 4, 5]) == 90

    class DB:
        calls = 0

        def scalars(self, stmt):
            self.calls += 1
            return iter([make_bars(), make_basis(), make_warehouse(), make_facts()][self.calls - 1])

    ctx = build_history_context(DB(), "20260108", windows=(5,))
    rb = ctx["RB"]
    assert rb["status"] == "ok"
    assert rb["highlights"]
    volume = next(x for x in rb["metrics"] if x["key"] == "volume")
    assert volume["percentile"] >= 90
    basis = next(x for x in rb["metrics"] if x["key"] == "basis_rate")
    warehouse = next(x for x in rb["metrics"] if x["key"] == "warehouse_delta")
    seat = next(x for x in rb["metrics"] if x["key"] == "seat_net_delta")
    assert basis["status"] == "ok"
    assert warehouse["percentile"] >= 90
    assert seat["percentile"] >= 90
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


def make_basis() -> list[BasisDaily]:
    return [BasisDaily(trade_date=f"202601{idx:02d}", symbol="RB", basis_rate=value) for idx, value in enumerate([1, 2, 3, 4, 5, 6, 7, 8], 1)]


def make_warehouse() -> list[WarehouseReceiptDaily]:
    return [WarehouseReceiptDaily(trade_date=f"202601{idx:02d}", symbol="RB", increase_number=value) for idx, value in enumerate([10, 20, 30, 40, 50, 60, 70, 300], 1)]


def make_facts() -> list[VarietyDailyFact]:
    return [VarietyDailyFact(trade_date=f"202601{idx:02d}", exchange="SHFE", symbol="RB", archive_net_delta=value) for idx, value in enumerate([100, 200, 300, 400, 500, 600, 700, 2000], 1)]


if __name__ == "__main__":
    check()
    print("ok")
