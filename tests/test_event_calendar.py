from __future__ import annotations

from app.services.event_calendar import build_event_calendar


def check() -> None:
    digest = build_event_calendar("20260523", window_days=10)
    assert digest["trade_date"] == "20260523"
    assert digest["summary"]["count"] >= 1
    assert digest["summary"]["next_event"]
    assert any(item["title"] == "美国 EIA 原油库存" for item in digest["items"])
    assert {"name": "manual", "status": "optional", "note": "config/event_calendar.json 手动导入"} in digest["sources"]


if __name__ == "__main__":
    check()
    print("ok")
