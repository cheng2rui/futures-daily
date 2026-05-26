from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CrawlerRun, DailyBar, SeatRankRow
from app.services.retry_planner import build_retry_plan


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        trade_date = "20260523"
        # Keep one exchange mostly covered so the planner focuses on actual gaps.
        db.add(DailyBar(trade_date=trade_date, exchange="SHFE", symbol="RU", contract="RU2609", close=1, volume=1, open_interest=1))
        db.add(SeatRankRow(trade_date=trade_date, exchange="SHFE", variety="RU", rank=1, long_party_name="测试", long_open_interest=1))
        db.add(CrawlerRun(trade_date=trade_date, exchange="DCE", kind="seat_rank", source="akshare", status="failed", error="empty seat rank"))
        db.commit()

        plan = build_retry_plan(db, trade_date)
        assert plan["trade_date"] == trade_date
        assert plan["summary"]["steps"] >= 1
        assert any(step["type"] == "recollect" and step["exchange"] == "DCE" and step["kind"] == "daily" for step in plan["steps"])
        dce_seat = next(step for step in plan["steps"] if step["type"] == "recollect" and step["exchange"] == "DCE" and step["kind"] == "seat_rank")
        assert dce_seat["decision"] == "retry_verify_params"
        assert dce_seat["error_category"]["code"] == "empty"
        assert dce_seat["browser_probe"]["provider"] == "cloakbrowser"
        assert dce_seat["browser_probe"]["source"] == "dce_official_cloakbrowser"
        assert any(step["type"] == "collect_quhe" and step["decision"] == "retry_enhancement_bundle" for step in plan["steps"])
        assert any(item["exchange"] == "INE" and item["kind"] == "seat_rank" and item["reason_code"] == "not_supported" and item["executable"] is False for item in plan["skipped"])
        ine_seat = next(item for item in plan["skipped"] if item["exchange"] == "INE" and item["kind"] == "seat_rank")
        assert ine_seat["source"] == "akshare"
        assert ine_seat["diagnostic_hint"]
        assert plan["summary"]["skipped_by_reason"].get("not_supported", 0) >= 1
        assert plan["summary"]["skipped_by_kind"].get("seat_rank", 0) >= 1
        assert plan["summary"]["skipped_samples"]
        priorities = [step["priority"] for step in plan["steps"]]
        assert priorities == sorted(priorities)
        assert all(step["order"] >= 1 for step in plan["steps"])
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
