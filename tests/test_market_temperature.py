from app.models import DailyBar
from app.services.report_builder import build_market_temperature


def bar(symbol, contract, close, pre_close, oi, volume=10000, exchange="SHFE"):
    return DailyBar(
        trade_date="2026-05-24",
        exchange=exchange,
        symbol=symbol,
        contract=contract,
        close=close,
        pre_close=pre_close,
        open_interest=oi,
        volume=volume,
    )


def key(b):
    return (b.exchange, b.symbol.upper(), str(b.contract or ""))


def test_short_side_can_be_high_temperature():
    rb = bar("RB", "RB2609", 95, 100, 12000)
    hc = bar("HC", "HC2609", 96, 100, 9000)
    result = build_market_temperature(
        ranking_valid=[(rb, -5.0), (hc, -4.0)],
        main_bars=[rb, hc],
        main_oi_deltas={key(rb): 2000, key(hc): 1200},
        sectors=[{"name": "黑色", "count": 2, "up": 0, "down": 2}],
        volume_delta_pct=28,
        capital_flow_amount=-8_000_000_000,
        capital_inflow_amount=1_000_000_000,
        capital_outflow_amount=-9_000_000_000,
        total_oi_delta=3200,
        total_oi=21000,
    )
    assert result["score"] >= 70
    assert result["direction"] == "空方占优"
    assert result["heat"].endswith("｜空方占优")


def test_shrinking_quiet_market_is_low_temperature():
    rb = bar("RB", "RB2609", 100.05, 100, 8000)
    result = build_market_temperature(
        ranking_valid=[(rb, 0.05)],
        main_bars=[rb],
        main_oi_deltas={key(rb): -1500},
        sectors=[{"name": "黑色", "count": 1, "up": 0, "down": 0}],
        volume_delta_pct=-35,
        capital_flow_amount=-1_000_000_000,
        capital_inflow_amount=0,
        capital_outflow_amount=-1_000_000_000,
        total_oi_delta=-1500,
        total_oi=8000,
    )
    assert result["score"] < 40
    assert result["direction"] == "资金退潮"


if __name__ == "__main__":
    test_short_side_can_be_high_temperature()
    test_shrinking_quiet_market_is_low_temperature()
    print("ok")
