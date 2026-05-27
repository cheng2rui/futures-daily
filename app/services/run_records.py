from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def complete_state_from_coverage(coverage_matrix: dict[str, Any] | None, report_status: str = "") -> str:
    """Return complete/partial/error for promotion to current report state.

    A state is complete only when a report exists and all core exchange cells are
    usable. Partial is still promotable but must remain visibly caveated. Error
    means the run should not be treated as a usable current-state source.
    """
    if report_status == "blocked":
        return "error"
    matrix = coverage_matrix or {}
    summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}
    core_pct = float(summary.get("core_coverage_pct") or 0)
    status = str(summary.get("status") or "")
    if core_pct >= 100 and status == "ok":
        return "complete"
    if core_pct > 0:
        return "partial"
    return "error"


def coverage_counts(coverage_matrix: dict[str, Any] | None) -> dict[str, int]:
    summary = (coverage_matrix or {}).get("summary") if isinstance((coverage_matrix or {}).get("summary"), dict) else {}
    rows = (coverage_matrix or {}).get("rows") if isinstance((coverage_matrix or {}).get("rows"), list) else []
    return {
        "exchanges": int(summary.get("exchanges") or len(rows) or 0),
        "ok_exchanges": int(summary.get("ok_exchanges") or 0),
        "partial_exchanges": int(summary.get("partial_exchanges") or 0),
        "failed_exchanges": int(summary.get("failed_exchanges") or 0),
        "core_coverage_pct_x10": int(round(float(summary.get("core_coverage_pct") or 0) * 10)),
        "overall_coverage_pct_x10": int(round(float(summary.get("overall_coverage_pct") or 0) * 10)),
    }


def stable_record_id(record_type: str, *parts: Any) -> str:
    raw = json.dumps([record_type, *parts], ensure_ascii=False, sort_keys=True, default=str)
    return f"{record_type}:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def run_summary(*, run_id: str, trade_date: str, profile: str, status: str, counts: dict[str, int] | None = None, error: str = "", started_at: datetime | None = None) -> dict[str, Any]:
    end = datetime.utcnow()
    payload = {
        "record_type": "run_summary",
        "run_id": run_id,
        "trade_date": trade_date,
        "profile": profile,
        "status": status,
        "counts": counts or {},
        "error": error,
        "end_time": end.isoformat(),
    }
    if started_at:
        payload["start_time"] = started_at.isoformat()
        payload["duration_ms"] = int((end - started_at).total_seconds() * 1000)
    payload["record_id"] = stable_record_id("run_summary", run_id, trade_date, profile, status, payload.get("counts"))
    return payload


def source_record_id(*, trade_date: str, exchange: str, kind: str, source: str, source_file: str = "", parser_version: str = "") -> str:
    return stable_record_id("source_record", trade_date, exchange, kind, source, source_file, parser_version)
