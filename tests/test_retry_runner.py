from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.retry_runner import archive_materialization_effect, run_retry_plan


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


def check_archive_materialization_effect_aliases() -> None:
    signals = {
        "source": "rsstsx_archive",
        "count": 12,
        "net_delta_top": [{"displayName": "豆粕", "exchange": "DCE", "netDelta": -123, "netDir": "偏空"}],
        "focus5": {"combined_by_variety": [{"variety": "M", "exchange": "DCE", "netDelta": -321, "netVol": 88}]},
    }
    materialized = {"summary": {"exchanges": [{"exchange": "DCE", "varieties": 20, "with_archive_signal": 8}, {"exchange": "SHFE", "varieties": 10, "with_archive_signal": 2}]}}

    effect = archive_materialization_effect(signals, materialized, "DCE")

    assert effect["exchange"] == "DCE"
    assert effect["archive_count"] == 12
    assert effect["rsstsx_varieties"] == 12
    assert effect["varieties"] == 20
    assert effect["with_archive_signal"] == 8
    assert effect["coverage_pct"] == 40.0
    assert effect["top_net_delta"] == effect["top_net_delta_samples"]
    assert effect["focus5"] == effect["focus5_samples"]
    assert effect["top_net_delta_samples"][0]["name"] == "豆粕"
    assert "DCE 物化结构信号 8/20" in effect["summary"]


if __name__ == "__main__":
    check()
    check_archive_materialization_effect_aliases()
    print("ok")
