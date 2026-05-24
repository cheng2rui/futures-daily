from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import JobRun
from app.services.retry_history import list_retry_runs


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        payload = {
            "initial_plan": {"summary": {"summary": "建议执行 2 个步骤。"}, "steps": [{}, {}]},
            "executed": [
                {
                    "step": {"type": "recollect", "exchange": "DCE", "kind": "daily", "priority": 10},
                    "status": "success",
                    "summary": "改善 2 项",
                    "coverage_diff": {
                        "improved_cells": 2,
                        "regressed_cells": 0,
                        "core_coverage_after": 60,
                        "changes": [
                            {
                                "exchange": "DCE",
                                "kind": "daily",
                                "direction": "improved",
                                "before": {"status": "missing", "rows": 0},
                                "after": {"status": "ok", "rows": 24},
                                "row_delta": 24,
                            }
                        ],
                    },
                },
                {
                    "step": {"type": "collect_quhe", "exchange": "ALL", "kind": "basis", "priority": 40},
                    "status": "failed",
                    "error": "timeout",
                    "coverage_diff": {
                        "improved_cells": 0,
                        "regressed_cells": 1,
                        "overall_coverage_after": 70,
                        "changes": [
                            {
                                "exchange": "INE",
                                "kind": "basis",
                                "direction": "regressed",
                                "before": {"status": "ok", "rows": 6},
                                "after": {"status": "missing", "rows": 0},
                                "row_delta": -6,
                            }
                        ],
                    },
                },
            ],
            "after_plan": {"summary": {"summary": "还剩 1 步。"}, "steps": [{}], "skipped": [{}, {}]},
        }
        db.add(JobRun(name="retry_plan", status="partial", trade_date="20260523", started_at=datetime.utcnow(), finished_at=datetime.utcnow(), message="执行 2 步", result_json=json.dumps(payload, ensure_ascii=False)))
        db.add(JobRun(name="generate_report", status="success", trade_date="20260523", started_at=datetime.utcnow(), finished_at=datetime.utcnow(), message="ignore", result_json="{}"))
        db.commit()

        result = list_retry_runs(db, "20260523", limit=10)
        assert result["summary"]["total"] == 1
        assert result["summary"]["partial"] == 1
        assert result["summary"]["improved_cells"] == 2
        run = result["runs"][0]
        assert run["steps_total"] == 2
        assert run["steps_failed"] == 1
        assert run["remaining_steps"] == 1
        assert run["remaining_skipped"] == 2
        assert run["coverage_diff"]["improved_cells"] == 2
        assert run["coverage_diff"]["regressed_cells"] == 1
        assert run["coverage_diff"]["changed_cells"] == 2
        assert run["cell_changes"][0]["exchange"] == "DCE"
        assert run["cell_changes"][0]["summary"] == "missing/0 → ok/24，行数 +24"
        assert "改善 1 格" in run["change_summary"]
        assert run["executed"][0]["exchange"] == "DCE"
        assert run["executed"][0]["changes"][0]["kind"] == "daily"
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
