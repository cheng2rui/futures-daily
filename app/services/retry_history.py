from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import JobRun


def list_retry_runs(db: Session, trade_date: str | None = None, *, limit: int = 20) -> dict[str, Any]:
    """Return compact retry-run history for diagnostics UI.

    Retry Runner stores durable execution records in JobRun.result_json. This
    helper normalizes those records into a stable API shape so the frontend can
    show what was executed, how much coverage changed, and what remains.
    """
    stmt = select(JobRun).where(JobRun.name == "retry_plan").order_by(desc(JobRun.started_at)).limit(max(1, min(int(limit or 20), 100)))
    if trade_date:
        stmt = stmt.where(JobRun.trade_date == trade_date)
    rows = db.scalars(stmt).all()
    items = [serialize_retry_run(row) for row in rows]
    return {
        "trade_date": trade_date or "",
        "limit": limit,
        "summary": summarize_retry_runs(items),
        "runs": items,
    }


def serialize_retry_run(row: JobRun) -> dict[str, Any]:
    payload = parse_json(row.result_json)
    executed = payload.get("executed") if isinstance(payload.get("executed"), list) else []
    after_plan = payload.get("after_plan") if isinstance(payload.get("after_plan"), dict) else {}
    initial_plan = payload.get("initial_plan") if isinstance(payload.get("initial_plan"), dict) else {}
    failures = [x for x in executed if x.get("status") == "failed"]
    improved = sum(int((x.get("coverage_diff") or {}).get("improved_cells") or 0) for x in executed)
    regressed = sum(int((x.get("coverage_diff") or {}).get("regressed_cells") or 0) for x in executed)
    last_diff = next((x.get("coverage_diff") for x in reversed(executed) if x.get("coverage_diff")), {}) or {}
    return {
        "id": row.id,
        "status": row.status,
        "trade_date": row.trade_date,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "message": row.message,
        "steps_total": len(executed),
        "steps_failed": len(failures),
        "improved_cells": improved,
        "regressed_cells": regressed,
        "coverage_diff": {
            **last_diff,
            "improved_cells": improved,
            "regressed_cells": regressed,
        },
        "remaining_steps": len(after_plan.get("steps") or []),
        "remaining_skipped": len(after_plan.get("skipped") or []),
        "initial_summary": (initial_plan.get("summary") or {}).get("summary", ""),
        "after_summary": (after_plan.get("summary") or {}).get("summary", ""),
        "executed": [serialize_retry_step(x) for x in executed],
    }


def serialize_retry_step(step_result: dict[str, Any]) -> dict[str, Any]:
    step = step_result.get("step") if isinstance(step_result.get("step"), dict) else {}
    diff = step_result.get("coverage_diff") if isinstance(step_result.get("coverage_diff"), dict) else {}
    return {
        "type": step.get("type", ""),
        "exchange": step.get("exchange", ""),
        "kind": step.get("kind", ""),
        "priority": step.get("priority"),
        "status": step_result.get("status", ""),
        "error": step_result.get("error", ""),
        "summary": step_result.get("summary") or diff.get("summary") or "",
        "improved_cells": int(diff.get("improved_cells") or 0),
        "regressed_cells": int(diff.get("regressed_cells") or 0),
        "started_at": step_result.get("started_at"),
        "finished_at": step_result.get("finished_at"),
    }


def summarize_retry_runs(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    failed = sum(1 for x in items if x.get("status") == "failed")
    partial = sum(1 for x in items if x.get("status") == "partial")
    success = sum(1 for x in items if x.get("status") == "success")
    improved = sum(int(x.get("improved_cells") or 0) for x in items)
    regressed = sum(int(x.get("regressed_cells") or 0) for x in items)
    return {
        "total": total,
        "success": success,
        "partial": partial,
        "failed": failed,
        "improved_cells": improved,
        "regressed_cells": regressed,
        "summary": f"最近 {total} 次执行：成功 {success} 次，部分成功 {partial} 次，失败 {failed} 次；累计改善 {improved} 项。" if total else "暂无自动补采执行历史。",
    }


def parse_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001
        return {}
