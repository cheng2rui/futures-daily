from __future__ import annotations

from app.models import DailyBar
from app.services.term_structure import build_term_structure, contract_sort_key


def check() -> None:
    assert contract_sort_key("RB2601")[0] == 202601
    assert contract_sort_key("TA609")[0] == 202609

    digest = build_term_structure([
        DailyBar(exchange="SHFE", symbol="RB", contract="RB2601", close=3300, pre_close=3290, volume=1000, open_interest=10000),
        DailyBar(exchange="SHFE", symbol="RB", contract="RB2605", close=3350, pre_close=3320, volume=5000, open_interest=50000),
        DailyBar(exchange="SHFE", symbol="RB", contract="RB2610", close=3400, pre_close=3370, volume=3000, open_interest=30000),
    ])
    assert digest["count"] == 1
    item = digest["items"][0]
    assert item["structure_type"] == "contango"
    assert item["main_contract"] == "RB2605"
    assert item["near_far_spread"]["value"] == -100
    assert item["main_second_spread"]
    assert "升水结构" in item["summary"]


if __name__ == "__main__":
    check()
    print("ok")
