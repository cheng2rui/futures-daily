from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.raw_archive import archive_payload
from app.services.raw_replay import replay_source_file


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_raw_replay"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        daily = archive_payload(
            db,
            trade_date="20260523",
            exchange="DCE",
            kind="daily",
            source="unit",
            payload={"rows": [{"contract": "a2607", "close": "4012", "volume": "100"}, {"bad": "row"}]},
        )
        seat = archive_payload(
            db,
            trade_date="20260523",
            exchange="SHFE",
            kind="seat_rank",
            source="unit",
            payload={"rows": [{"symbol": "RU2609", "rank": "1", "long_party_name": "永安期货", "long_open_interest": "10"}]},
        )
        unsupported = archive_payload(
            db,
            trade_date="20260523",
            exchange="ALL",
            kind="basis",
            source="unit",
            payload={"rows": [{"x": 1}]},
        )
        browser = archive_payload(
            db,
            trade_date="20260523",
            exchange="DCE",
            kind="seat_rank_browser_probe",
            source="unit_browser",
            payload={"ok": True, "url": "https://www.dce.com.cn/x/y/", "status": 200, "title": "DCE", "html": "<a href='../files/rank.xlsx'>会员持仓排名 Excel</a><table><tr><th>名次</th><th>会员简称</th><th>持买单量</th></tr><tr><td>1</td><td>永安期货</td><td>100</td></tr></table><p>成交 持仓 排名</p>", "webdriver": False, "user_agent": "test"},
        )
        db.commit()

        daily_result = replay_source_file(db, daily.id)
        assert daily_result["status"] == "partial"
        assert daily_result["input_rows"] == 2
        assert daily_result["parsed_rows"] == 1
        assert daily_result["sample"][0]["symbol"] == "A"
        assert daily_result["stats"]["contracts"] == 1

        seat_result = replay_source_file(db, seat.id)
        assert seat_result["status"] == "ok"
        assert seat_result["parsed_rows"] == 1
        assert seat_result["sample"][0]["variety"] == "RU"

        unsupported_result = replay_source_file(db, unsupported.id)
        assert unsupported_result["status"] == "unsupported"
        assert unsupported_result["input_rows"] == 1

        browser_result = replay_source_file(db, browser.id)
        assert browser_result["status"] == "ok"
        sample = browser_result["sample"][0]
        assert sample["signals"]["contains_table"] is True
        assert sample["signals"]["contains_position_keywords"] is True
        assert browser_result["stats"]["contains_table"] is True
        assert browser_result["stats"]["table_candidates"] == 1
        assert browser_result["stats"]["excel_links"] == 1
        assert browser_result["stats"]["keyword_blocks"] >= 1
        assert sample["candidates"]["tables"][0]["headers"] == ["名次", "会员简称", "持买单量"]
        assert sample["candidates"]["tables"][0]["sample_rows"][1][1] == "永安期货"
        assert sample["candidates"]["excel_links"][0]["absolute_url"] == "https://www.dce.com.cn/x/files/rank.xlsx"
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
