from __future__ import annotations

from app.api.assistant import answer_daily_question


REPORT = {
    "overview": {"stage": "偏弱", "summary": "市场整体偏弱，化工板块承压。"},
    "market": {"up_count": 10, "down_count": 20, "main_contracts": 50},
    "intelligence": {
        "abnormal_cards": [
            {
                "symbol": "TA",
                "name": "PTA",
                "signal": "放量下跌，偏弱",
                "evidence_chain": [{"label": "价格", "text": "主力跌 2%"}],
                "watch_next": "看是否继续增仓下跌",
            }
        ],
        "tomorrow_watch": [{"title": "关注 PTA", "body": "确认下跌是否延续", "category": "价格延续", "impact": "若延续下跌，继续重点观察"}],
        "watch_digest": {"summary": "自选整体偏弱", "items": [{"symbol": "TA", "name": "PTA", "signal": "偏弱"}]},
    },
    "data_quality": {"status": "partial", "overall_coverage_pct": 66.7, "summary": "部分交易所缺席位", "exchanges": [{"exchange": "DCE", "status": "partial", "note": "席位缺失"}]},
    "seats": {"archive": {"net_delta_top": [{"name": "PTA", "netDelta": -100, "netDir": "偏空"}]}, "long_increase_top": [], "short_increase_top": []},
}


def check() -> None:
    abnormal = answer_daily_question(REPORT, "今天哪些品种最异常？")
    assert abnormal["title"] == "今天哪些品种最值得关注？"
    assert "PTA" in abnormal["headline"]
    assert abnormal["bullets"]

    tomorrow = answer_daily_question(REPORT, "明天重点看什么？")
    assert tomorrow["title"] == "明天重点看什么？"
    assert "关注 PTA" in tomorrow["headline"]
    assert "价格延续" in tomorrow["bullets"][0]

    quality = answer_daily_question(REPORT, "数据够不够用？")
    assert quality["title"] == "数据够不够用？"
    assert "缺失" in quality["headline"]

    seats = answer_daily_question(REPORT, "席位有什么变化？")
    assert seats["bullets"]


if __name__ == "__main__":
    check()
    print("ok")
