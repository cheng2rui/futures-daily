from __future__ import annotations

from app.services.coverage_diff import diff_coverage_matrix


def check() -> None:
    before = {
        "summary": {"core_coverage_pct": 50.0, "overall_coverage_pct": 40.0},
        "rows": [
            {"exchange": "DCE", "cells": {"daily": {"status": "missing", "rows": 0}, "seat_rank": {"status": "failed", "rows": 0}}},
            {"exchange": "INE", "cells": {"daily": {"status": "ok", "rows": 5}, "seat_rank": {"status": "not_supported", "rows": 0}}},
        ],
    }
    after = {
        "summary": {"core_coverage_pct": 75.0, "overall_coverage_pct": 55.0},
        "rows": [
            {"exchange": "DCE", "cells": {"daily": {"status": "ok", "rows": 24}, "seat_rank": {"status": "failed", "rows": 0}}},
            {"exchange": "INE", "cells": {"daily": {"status": "ok", "rows": 5}, "seat_rank": {"status": "not_supported", "rows": 0}}},
        ],
    }

    diff = diff_coverage_matrix(before, after)
    assert diff["core_coverage_delta"] == 25.0
    assert diff["overall_coverage_delta"] == 15.0
    assert diff["improved_cells"] == 1
    assert diff["regressed_cells"] == 0
    assert diff["changed_cells"] == 1
    assert diff["changes"][0]["exchange"] == "DCE"
    assert diff["changes"][0]["kind"] == "daily"
    assert diff["changes"][0]["direction"] == "improved"
    assert "改善 1 项" in diff["summary"]

    same = diff_coverage_matrix(after, after)
    assert same["changed_cells"] == 0
    assert same["summary"] == "覆盖矩阵无变化。"


if __name__ == "__main__":
    check()
    print("ok")
