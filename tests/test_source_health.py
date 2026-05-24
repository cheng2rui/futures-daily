from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CrawlerRun, DataGap
from app.services.raw_archive import archive_payload
from app.services.source_health import build_source_health


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_source_health"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        trade_date = "20260523"
        db.add(CrawlerRun(trade_date=trade_date, exchange="DCE", kind="daily", source="akshare", status="success", rows=120, saved=120))
        db.add(CrawlerRun(trade_date=trade_date, exchange="DCE", kind="seat_rank", source="akshare", status="failed", rows=0, saved=0, error="empty seat rank"))
        db.add(DataGap(trade_date=trade_date, exchange="DCE", kind="seat_rank", severity="error", status="open", message="empty seat rank"))
        archive_payload(
            db,
            trade_date=trade_date,
            exchange="DCE",
            kind="daily",
            source="akshare",
            payload={"rows": [{"contract": "A2607"}] * 40},
        )
        db.commit()

        health = build_source_health(db, trade_date)
        assert health["trade_date"] == trade_date
        assert health["summary"]["total_sources"] >= 1
        ak = next(row for row in health["sources"] if row["source"] == "akshare")
        assert ak["runs_total"] == 2
        assert ak["runs_success"] == 1
        assert ak["runs_failed"] == 1
        assert ak["archives_count"] == 1
        assert ak["open_gaps"] == 1
        assert ak["latest_error"] == "empty seat rank"
        assert ak["latest_error_category"]["code"] == "empty"
        assert ak["error_summary"]["top_code"] == "empty"
        assert ak["latest_runs"][0]["error_category"]["code"] in {"empty", "unknown"}
        assert 0 <= ak["score"] <= 100
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
