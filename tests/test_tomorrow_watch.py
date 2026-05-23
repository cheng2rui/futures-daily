from __future__ import annotations

from app.services.report_builder import build_tomorrow_watch


def check() -> None:
    items = build_tomorrow_watch(
        abnormal_cards=[
            {
                "symbol": "TA",
                "name": "PTA",
                "score": 25,
                "signal": "放量下跌，偏空",
                "dimensions": [{"name": "席位净变化"}],
                "evidence_chain": [
                    {"key": "price", "text": "涨跌 -2%"},
                    {"key": "seat", "text": "净变化 -12000"},
                ],
                "watch_next": "看是否继续增仓下跌",
            }
        ],
        data_quality={"exchanges": [{"exchange": "DCE", "status": "partial", "note": "席位缺失"}]},
        gap_analysis={"actionable_count": 2},
        news_digest={"viewpoints": [{"symbol": "TA", "name": "PTA", "bias": "negative", "summary": "需求偏弱"}]},
    )

    assert items[0]["priority"] == "high"
    assert items[0]["category"] == "席位验证"
    assert items[0]["evidence"]
    assert any(x["category"] == "数据复核" for x in items)
    assert any(x.get("impact") for x in items)


if __name__ == "__main__":
    check()
    print("ok")
