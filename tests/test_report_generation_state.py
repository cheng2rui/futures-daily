from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.reports import annotate_latest_state, ensure_report_payload
from app.db import Base
from app.models import CrawlerRun, JobRun, Report
from app.services.run_records import run_summary
from app.services.report_builder import build_report


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        blocked = build_report(db, "20260526")
        payload = json.loads(blocked.report_json)
        assert blocked.status == "blocked"
        assert blocked.score == 0
        assert payload["meta"]["operational_status"] == "no_usable_market_data"
        assert payload["overview"]["stage"] == "无数据"
        assert "未找到可用日行情数据" in blocked.summary

        old_report = Report(
            trade_date="20260525",
            status="generated",
            score=60,
            summary="old",
            report_json=json.dumps({
                "date": "20260525",
                "meta": {"report_schema_version": 9},
                "overview": {"summary": "old"},
                "report_sections": [{}],
                "report_brief": {},
            }, ensure_ascii=False),
            generated_at=datetime.utcnow(),
        )
        db.add(old_report)
        db.add(CrawlerRun(trade_date="20260527", exchange="DCE", kind="daily", source="akshare", status="failed", error="network timeout"))
        db.add(JobRun(name="generate_report", status="success", trade_date="20260525", result_json=json.dumps({
            "run_summary": run_summary(run_id="generate_report:1", trade_date="20260525", profile="generate_report", status="partial", counts={"core_coverage_pct_x10": 800})
        }, ensure_ascii=False)))
        db.commit()

        stale_payload = annotate_latest_state(db, ensure_report_payload(db, old_report), old_report)
        assert stale_payload["meta"]["latest_state"]["status"] == "stale"
        assert stale_payload["meta"]["latest_state"]["latest_activity_date"] == "20260527"
        assert stale_payload["meta"]["current_state"]["status"] == "partial"
        assert stale_payload["meta"]["current_state"]["run_id"] == "generate_report:1"
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
