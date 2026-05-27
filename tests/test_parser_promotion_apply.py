from __future__ import annotations

import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DataGap, SeatRankRow
from app.services.raw_archive import archive_payload
from app.services.parser_promotion_apply import apply_promotion_preview, expected_confirm_token


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_promotion_apply"
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
        db.add(DataGap(trade_date="20260526", exchange="DCE", kind="seat_rank", status="open", severity="error", rows=0, message="missing"))
        db.commit()

        denied = apply_promotion_preview(db, file, confirm="WRONG")
        assert denied["status"] == "blocked"
        assert denied["inserted"] == 0
        assert denied["confirm_required"] == expected_confirm_token(file.id)
        assert db.scalar(select(SeatRankRow.id)) is None

        applied = apply_promotion_preview(db, file, confirm=expected_confirm_token(file.id))
        assert applied["status"] == "applied"
        assert applied["would_write"] is True
        assert applied["inserted"] == 6
        assert applied["skipped"] == 0
        assert db.scalars(select(SeatRankRow)).first().raw_json.find('"promotion": true') >= 0
        gap = db.scalar(select(DataGap).where(DataGap.trade_date == "20260526", DataGap.exchange == "DCE", DataGap.kind == "seat_rank"))
        assert gap.status == "resolved"
        assert gap.rows == 6

        again = apply_promotion_preview(db, file, confirm=expected_confirm_token(file.id))
        assert again["status"] == "noop"
        assert again["inserted"] == 0
        assert again["skipped"] == 6
        assert len(db.scalars(select(SeatRankRow)).all()) == 6
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
