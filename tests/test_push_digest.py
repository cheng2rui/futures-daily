from __future__ import annotations

from app.services.push_digest import build_push_digest


def check() -> None:
    digest = build_push_digest(
        {
            "date": "20260523",
            "overview": {"stage": "结构性分化", "score": 72, "summary": "黑色偏弱，化工分化。"},
            "market": {"up_count": 12, "down_count": 28},
            "intelligence": {
                "abnormal_cards": [
                    {"name": "PTA", "symbol": "TA", "signal": "放量下跌", "reasons": ["价格跌幅居前", "席位净空增加"]}
                ],
                "watch_digest": {"summary": "自选里 PTA 风险最高", "items": [{"name": "PTA", "change_pct": -2.12, "signal": "放量下跌", "status": "ok"}]},
                "news_digest": {"viewpoints": [{"name": "PTA", "bias": "negative", "summary": "需求偏弱，库存压力待确认"}]},
                "tomorrow_watch": [
                    {
                        "category": "席位验证",
                        "title": "PTA后续验证",
                        "body": "看是否继续增仓下跌。",
                        "priority": "high",
                        "evidence": ["价格跌幅居前", "席位净空增加"],
                        "impact": "若继续同向验证，应保持在重点观察名单。",
                    }
                ],
            },
            "data_quality": {"coverage_pct": 83},
        }
    )

    text = digest["text"]
    assert "【期货日报 2026-05-23】" in text
    assert "明日观察" in text
    assert "! 席位验证｜PTA后续验证" in text
    assert "证据：价格跌幅居前；席位净空增加" in text
    assert "影响：若继续同向验证" in text
    assert len(digest["brief"]) <= 1200


if __name__ == "__main__":
    check()
    print("ok")
