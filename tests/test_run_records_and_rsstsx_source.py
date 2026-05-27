from __future__ import annotations

from app.services.run_records import complete_state_from_coverage, coverage_counts, run_summary, source_record_id, stable_record_id
from app.sources.rsstsx_archive_source import RsstsxArchiveSource, to_provider_row


def check() -> None:
    a = stable_record_id("package", "x", 1)
    b = stable_record_id("package", "x", 1)
    c = stable_record_id("package", "x", 2)
    assert a == b
    assert a != c
    assert source_record_id(trade_date="20260526", exchange="DCE", kind="seat_rank", source="unit") == source_record_id(trade_date="20260526", exchange="DCE", kind="seat_rank", source="unit")
    summary = run_summary(run_id="r1", trade_date="20260526", profile="browser_probe", status="complete", counts={"source_record": 1})
    assert summary["record_type"] == "run_summary"
    assert summary["record_id"].startswith("run_summary:")
    matrix = {"summary": {"status": "ok", "exchanges": 6, "ok_exchanges": 6, "core_coverage_pct": 100, "overall_coverage_pct": 80}, "rows": []}
    assert complete_state_from_coverage(matrix, "generated") == "complete"
    assert coverage_counts(matrix)["core_coverage_pct_x10"] == 1000
    assert complete_state_from_coverage({"summary": {"status": "partial", "core_coverage_pct": 50}}, "generated") == "partial"
    assert complete_state_from_coverage(matrix, "blocked") == "error"

    src = RsstsxArchiveSource()
    caps = src.capabilities()
    assert caps[0].kind == "seat_archive_signal"
    row = to_provider_row({"name": "RU", "exchange": "SHFE", "longShortRatio": 1.2, "netDelta": 10})
    assert row["variety"] == "RU"
    assert row["net_delta"] == 10


if __name__ == "__main__":
    check()
    print("ok")
