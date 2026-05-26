from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.raw_archive import archive_payload
from app.services.parser_promotion_preview import build_promotion_preview


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_promotion_preview"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        headers = ["名次", "会员简称", "成交量", "成交量增减", "持买单量", "持买单量增减", "持卖单量", "持卖单量增减"]
        rows = [headers]
        for i in range(1, 7):
            rows.append([str(i), f"测试期货{i}", str(1000 - i), "1", str(800 - i), "2", str(700 - i), "-1"])
        file = archive_payload(
            db,
            trade_date="20260526",
            exchange="DCE",
            kind="seat_rank_browser_probe",
            source="unit_browser",
            payload={"ok": True, "url": "https://www.dce.com.cn/", "status": 200, "title": "DCE", "html": table_html(rows), "webdriver": False, "user_agent": "test"},
        )
        db.commit()
        preview = build_promotion_preview(file)
        assert preview["status"] == "ready"
        assert preview["would_write"] is False
        assert preview["promotion_guard"]["allowed"] is True
        assert preview["preview_count"] >= 5
        assert preview["preview_rows"][0]["vol_party_name"] == "测试期货1"
        assert preview["preview_rows"][0]["record_id"].startswith("seat_rank_preview:")
        assert preview["preview_rows"][0]["source_file_id"] == file.id
        assert preview["preview_rows"][0]["trade_date"] == "20260526"

        blocked_file = archive_payload(
            db,
            trade_date="20260526",
            exchange="DCE",
            kind="seat_rank_browser_probe",
            source="unit_browser",
            payload={"ok": True, "url": "https://www.dce.com.cn/", "status": 200, "title": "DCE", "html": table_html([headers, ["1", "测试", "1", "0", "1", "0", "1", "0"]]), "webdriver": False, "user_agent": "test"},
        )
        db.commit()
        blocked = build_promotion_preview(blocked_file)
        assert blocked["status"] == "blocked"
        assert blocked["preview_rows"] == []
    finally:
        db.close()


def table_html(rows: list[list[str]]) -> str:
    out = ["<table>"]
    for idx, row in enumerate(rows):
        tag = "th" if idx == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in row) + "</tr>")
    out.append("</table><p>会员持仓排名 成交 持仓 排名</p>")
    return "".join(out)


if __name__ == "__main__":
    check()
    print("ok")
