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
    cell_changes = aggregate_cell_changes(executed)
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
            "changes": cell_changes,
            "changed_cells": len(cell_changes),
        },
        "remaining_steps": len(after_plan.get("steps") or []),
        "remaining_skipped": len(after_plan.get("skipped") or []),
        "initial_summary": (initial_plan.get("summary") or {}).get("summary", ""),
        "after_summary": (after_plan.get("summary") or {}).get("summary", ""),
        "cell_changes": cell_changes,
        "change_summary": summarize_cell_changes(cell_changes),
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
        "changes": serialize_cell_changes(diff.get("changes") if isinstance(diff.get("changes"), list) else []),
        "started_at": step_result.get("started_at"),
        "finished_at": step_result.get("finished_at"),
    }


def aggregate_cell_changes(executed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-step coverage changes into final cell-level transitions.

    A retry run may touch the same exchange/kind more than once. For history we
    keep the first before-state and the latest after-state, while summing row
    deltas and preserving the final direction.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for step_result in executed:
        diff = step_result.get("coverage_diff") if isinstance(step_result.get("coverage_diff"), dict) else {}
        for change in diff.get("changes") or []:
            if not isinstance(change, dict):
                continue
            exchange = str(change.get("exchange") or "")
            kind = str(change.get("kind") or "")
            if not exchange or not kind:
                continue
            key = (exchange, kind)
            item = merged.get(key)
            if item is None:
                item = {**change, "steps": 0, "row_delta": 0}
                merged[key] = item
            else:
                item["after"] = change.get("after") or item.get("after") or {}
                item["direction"] = change.get("direction") or item.get("direction")
            item["row_delta"] = int(item.get("row_delta") or 0) + int(change.get("row_delta") or 0)
            item["steps"] = int(item.get("steps") or 0) + 1
    changes = serialize_cell_changes(list(merged.values()))
    return sorted(changes, key=lambda x: (change_rank(str(x.get("direction") or "")), x.get("exchange", ""), x.get("kind", "")))


def serialize_cell_changes(changes: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        before = change.get("before") if isinstance(change.get("before"), dict) else {}
        after = change.get("after") if isinstance(change.get("after"), dict) else {}
        out.append({
            "exchange": change.get("exchange", ""),
            "kind": change.get("kind", ""),
            "direction": change.get("direction", "changed"),
            "row_delta": int(change.get("row_delta") or 0),
            "before": {"status": before.get("status", ""), "rows": int(before.get("rows") or 0), "message": before.get("message") or ""},
            "after": {"status": after.get("status", ""), "rows": int(after.get("rows") or 0), "message": after.get("message") or ""},
            "steps": int(change.get("steps") or 1),
            "summary": cell_change_summary(change),
        })
    return out


def cell_change_summary(change: dict[str, Any]) -> str:
    before = change.get("before") if isinstance(change.get("before"), dict) else {}
    after = change.get("after") if isinstance(change.get("after"), dict) else {}
    row_delta = int(change.get("row_delta") or 0)
    delta = f"，行数 {row_delta:+d}" if row_delta else ""
    return f"{before.get('status', '-')}/{int(before.get('rows') or 0)} → {after.get('status', '-')}/{int(after.get('rows') or 0)}{delta}"


def summarize_cell_changes(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return "覆盖格子无变化。"
    improved = sum(1 for x in changes if x.get("direction") == "improved")
    regressed = sum(1 for x in changes if x.get("direction") == "regressed")
    changed = len(changes) - improved - regressed
    parts = []
    if improved:
        parts.append(f"改善 {improved} 格")
    if regressed:
        parts.append(f"回退 {regressed} 格")
    if changed:
        parts.append(f"变化 {changed} 格")
    top = "、".join(f"{x.get('exchange')} {x.get('kind')}" for x in changes[:3])
    return "；".join(parts) + (f"：{top}" if top else "")


def change_rank(direction: str) -> int:
    return {"improved": 0, "regressed": 1, "changed": 2}.get(direction, 3)


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
