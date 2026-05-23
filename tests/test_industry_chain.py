from __future__ import annotations

from app.services.industry_chain import build_industry_chain_digest


def check() -> None:
    dataset = {
        "rows": [
            {"symbol": "PX", "name": "PX", "main_contract": "PX2607", "main_change_pct": 2.2, "total_volume": 1200000, "total_open_interest": 300000},
            {"symbol": "TA", "name": "PTA", "main_contract": "TA2609", "main_change_pct": 1.6, "total_volume": 1500000, "total_open_interest": 500000},
            {"symbol": "PF", "name": "短纤", "main_contract": "PF2606", "main_change_pct": -0.8, "total_volume": 300000, "total_open_interest": 120000},
            {"symbol": "RB", "name": "螺纹钢", "main_contract": "RB2605", "main_change_pct": -1.5, "total_volume": 1800000, "total_open_interest": 700000},
            {"symbol": "I", "name": "铁矿石", "main_contract": "I2605", "main_change_pct": -2.1, "total_volume": 900000, "total_open_interest": 420000},
        ]
    }
    abnormal_cards = [
        {"symbol": "PX", "score": 21, "signal": "上涨 + 席位净多增加", "bias": "positive"},
        {"symbol": "I", "score": 18, "signal": "下跌 + 席位净空增加", "bias": "negative"},
    ]
    digest = build_industry_chain_digest(dataset, abnormal_cards)
    assert digest["count"] >= 2
    chains = {x["id"]: x for x in digest["items"]}
    assert "energy_chemical" in chains
    chem = chains["energy_chemical"]
    assert chem["abnormal_count"] == 1
    assert chem["divergence_score"] > 0
    assert chem["leading_symbols"][0]["symbol"] == "PX"
    assert "能化链" in digest["summary"]
    black = chains["black"]
    assert black["direction"] == "weak"


if __name__ == "__main__":
    check()
    print("ok")
