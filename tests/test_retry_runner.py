from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.retry_runner import run_retry_plan


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        trade_date = "20260523"
        plan = {
            "trade_date": trade_date,
            "summary": {"summary": "建议执行 2 个步骤：核心补采 1 个，增强源刷新 1 个；跳过 0 个不可自动处理项。"},
            "steps": [
                {"type": "recollect", "exchange": "DCE", "kind": "daily", "priority": 10},
                {"type": "collect_quhe", "exchange": "ALL", "kind": "basis", "priority": 40},
            ],
            "skipped": [],
            "health_summary": {},
        }
        matrices = [
            {"summary": {"core_coverage_pct": 10.0, "overall_coverage_pct": 20.0}, "rows": []},
            {"summary": {"core_coverage_pct": 20.0, "overall_coverage_pct": 30.0}, "rows": []},
            {"summary": {"core_coverage_pct": 30.0, "overall_coverage_pct": 40.0}, "rows": []},
            {"summary": {"core_coverage_pct": 40.0, "overall_coverage_pct": 50.0}, "rows": []},
            {"summary": {"core_coverage_pct": 50.0, "overall_coverage_pct": 60.0}, "rows": []},
            {"summary": {"core_coverage_pct": 60.0, "overall_coverage_pct": 70.0}, "rows": []},
            {"summary": {"core_coverage_pct": 70.0, "overall_coverage_pct": 80.0}, "rows": []},
        ]
        with patch("app.services.retry_runner.build_retry_plan", side_effect=[plan, plan]), \
             patch("app.services.retry_runner.build_coverage_matrix", side_effect=matrices), \
             patch("app.services.retry_runner.collect_daily_market", return_value={"results": [{"saved": 3, "error": None}]}), \
             patch("app.services.retry_runner.collect_seat_ranks", return_value={"results": [{"saved": 0, "error": "missing"}]}), \
             patch("app.services.retry_runner.collect_quhe_enhancements", return_value={"results": {"basis": {"saved": 2}}}), \
             patch("app.services.retry_runner.materialize_variety_dataset", return_value={"count": 2}), \
             patch("app.services.retry_runner.build_report", return_value=type("R", (), {"status": "generated", "score": 66.0, "summary": "done"})()), \
             patch("app.services.retry_runner.diff_coverage_matrix", side_effect=[
                 {"summary": "改善 1 项；核心覆盖 +10.0%；综合覆盖 +10.0%", "improved_cells": 1, "regressed_cells": 0},
                 {"summary": "改善 2 项；核心覆盖 +20.0%；综合覆盖 +20.0%", "improved_cells": 2, "regressed_cells": 0},
                 {"summary": "改善 3 项；核心覆盖 +30.0%；综合覆盖 +30.0%", "improved_cells": 3, "regressed_cells": 0},
             ]):
            result = run_retry_plan(db, trade_date, max_steps=2, stop_on_failure=False, rebuild=True)

        assert result["trade_date"] == trade_date
        assert result["job_status"] in {"success", "partial"}
        assert len(result["executed"]) == 2
        assert result["executed"][0]["status"] == "success"
        assert result["executed"][1]["status"] == "success"
        assert result["executed"][0]["coverage_diff"]["improved_cells"] == 1
        assert result["executed"][1]["coverage_diff"]["improved_cells"] == 2
        assert result["after_plan"]["summary"]["summary"] == plan["summary"]["summary"]
        assert result["finalization"]["report"]["status"] == "generated"
        assert "执行 2 步" in result["summary"]
        assert "已重建日报" in result["summary"]
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
