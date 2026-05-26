from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


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
