from __future__ import annotations

from typing import Any


def diff_coverage_matrix(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two coverage matrices and summarize operational impact."""
    before_summary = before.get("summary") or {}
    after_summary = after.get("summary") or {}
    before_rows = {row.get("exchange"): row for row in before.get("rows", [])}
    after_rows = {row.get("exchange"): row for row in after.get("rows", [])}
    exchanges = sorted(set(before_rows) | set(after_rows))

    cell_changes: list[dict[str, Any]] = []
    improved = 0
    regressed = 0
    unchanged = 0
    for exchange in exchanges:
        b_cells = (before_rows.get(exchange) or {}).get("cells") or {}
        a_cells = (after_rows.get(exchange) or {}).get("cells") or {}
        kinds = sorted(set(b_cells) | set(a_cells))
        for kind in kinds:
            b = b_cells.get(kind) or {}
            a = a_cells.get(kind) or {}
            b_status = b.get("status") or "missing"
            a_status = a.get("status") or "missing"
            b_rows = int(b.get("rows") or 0)
            a_rows = int(a.get("rows") or 0)
            if b_status == a_status and b_rows == a_rows:
                unchanged += 1
                continue
            direction = classify_change(b_status, a_status, b_rows, a_rows)
            if direction == "improved":
                improved += 1
            elif direction == "regressed":
                regressed += 1
            else:
                unchanged += 1
            cell_changes.append({
                "exchange": exchange,
                "kind": kind,
                "before": {"status": b_status, "rows": b_rows, "message": b.get("message")},
                "after": {"status": a_status, "rows": a_rows, "message": a.get("message")},
                "direction": direction,
                "row_delta": a_rows - b_rows,
            })

    core_before = float(before_summary.get("core_coverage_pct") or 0)
    core_after = float(after_summary.get("core_coverage_pct") or 0)
    overall_before = float(before_summary.get("overall_coverage_pct") or 0)
    overall_after = float(after_summary.get("overall_coverage_pct") or 0)
    return {
        "core_coverage_before": core_before,
        "core_coverage_after": core_after,
        "core_coverage_delta": round(core_after - core_before, 1),
        "overall_coverage_before": overall_before,
        "overall_coverage_after": overall_after,
        "overall_coverage_delta": round(overall_after - overall_before, 1),
        "improved_cells": improved,
        "regressed_cells": regressed,
        "changed_cells": len(cell_changes),
        "unchanged_cells": unchanged,
        "changes": sorted(cell_changes, key=lambda x: (change_rank(x["direction"]), x["exchange"], x["kind"])),
        "summary": build_summary(core_after - core_before, overall_after - overall_before, improved, regressed, cell_changes),
    }


def classify_change(before_status: str, after_status: str, before_rows: int, after_rows: int) -> str:
    before_score = status_score(before_status, before_rows)
    after_score = status_score(after_status, after_rows)
    if after_score > before_score:
        return "improved"
    if after_score < before_score:
        return "regressed"
    if after_rows > before_rows:
        return "improved"
    if after_rows < before_rows:
        return "regressed"
    return "changed"


def status_score(status: str, rows: int) -> int:
    base = {
        "failed": 0,
        "missing": 1,
        "unsupported": 1,
        "not_supported": 1,
        "partial": 2,
        "fallback": 3,
        "ok": 4,
    }.get(status, 1)
    return base * 1000 + min(rows, 999)


def change_rank(direction: str) -> int:
    return {"improved": 0, "regressed": 1, "changed": 2}.get(direction, 3)


def build_summary(core_delta: float, overall_delta: float, improved: int, regressed: int, changes: list[dict[str, Any]]) -> str:
    if not changes:
        return "覆盖矩阵无变化。"
    parts = []
    if improved:
        parts.append(f"改善 {improved} 项")
    if regressed:
        parts.append(f"回退 {regressed} 项")
    if core_delta:
        parts.append(f"核心覆盖 {core_delta:+.1f}%")
    if overall_delta:
        parts.append(f"综合覆盖 {overall_delta:+.1f}%")
    if not parts:
        parts.append(f"变化 {len(changes)} 项")
    return "；".join(parts) + "。"
