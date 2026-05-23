from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.coverage_matrix import build_coverage_matrix
from app.services.source_health import build_source_health

CORE_KINDS = {"daily", "seat_rank"}
ENHANCEMENT_KINDS = {"capital_flow", "basis", "warehouse_receipt"}


def build_retry_plan(db: Session, trade_date: str) -> dict[str, Any]:
    coverage = build_coverage_matrix(db, trade_date, sync_gaps=False)
    health = build_source_health(db, trade_date)
    health_by_source = {row["source"]: row for row in health.get("sources", [])}
    steps: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in coverage.get("rows", []):
        exchange = row.get("exchange")
        cells = row.get("cells") or {}
        for kind, cell in cells.items():
            status = cell.get("status")
            if status in {"ok", "fallback"}:
                continue
            if status == "not_supported":
                skipped.append(skip_item(exchange, kind, cell, "not_supported"))
                continue
            if kind in CORE_KINDS:
                steps.append(core_step(trade_date, exchange, kind, cell, health_by_source))
            elif kind in ENHANCEMENT_KINDS:
                steps.append(enhancement_step(trade_date, exchange, kind, cell, health_by_source))
            elif kind == "archive_signal":
                skipped.append(skip_item(exchange, kind, cell, "archive_dependency"))

    steps = merge_enhancement_steps(steps)
    steps.sort(key=lambda x: (x["priority"], x["exchange"], x["kind"]))
    for idx, step in enumerate(steps, start=1):
        step["order"] = idx
    return {
        "trade_date": trade_date,
        "summary": plan_summary(steps, skipped),
        "steps": steps,
        "skipped": skipped,
        "health_summary": health.get("summary") or {},
    }


def core_step(trade_date: str, exchange: str, kind: str, cell: dict[str, Any], health_by_source: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = recommended_source(exchange, kind)
    source_health = health_by_source.get(source) or {}
    status = source_health.get("status") or "unknown"
    priority = 10 if kind == "daily" else 20
    if cell.get("status") == "failed":
        priority -= 3
    if status == "bad":
        priority += 6
    return {
        "type": "recollect",
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "source_status": status,
        "priority": priority,
        "endpoint": f"POST /api/reports/{trade_date}/recollect?exchange={exchange}&kinds={kind}&rebuild=true",
        "reason": f"{exchange} {kind} 当前 {cell.get('status')}：{cell.get('message') or '数据缺失'}",
        "expected_effect": "补齐核心覆盖并刷新日报" if kind == "daily" else "补齐席位覆盖；若源不可用会保留 data_gap",
        "risk": risk_note(source, status, exchange, kind),
    }


def enhancement_step(trade_date: str, exchange: str, kind: str, cell: dict[str, Any], health_by_source: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = enhancement_source(kind)
    source_health = health_by_source.get(source) or {}
    status = source_health.get("status") or "unknown"
    priority = 40 if kind == "capital_flow" else 45
    if status == "bad":
        priority += 8
    return {
        "type": "collect_quhe",
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "source_status": status,
        "priority": priority,
        "endpoint": f"POST /api/dataset/collect-quhe/{trade_date}",
        "reason": f"{exchange} {kind} 当前 {cell.get('status')}：{cell.get('message') or '增强数据缺失'}",
        "expected_effect": "刷新曲合/官方增强数据后重新物化数据集",
        "risk": risk_note(source, status, exchange, kind),
    }


def merge_enhancement_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    quhe_steps = [s for s in steps if s["type"] == "collect_quhe"]
    non_quhe = [s for s in steps if s["type"] != "collect_quhe"]
    out.extend(non_quhe)
    if quhe_steps:
        exchanges = sorted({s["exchange"] for s in quhe_steps})
        kinds = sorted({s["kind"] for s in quhe_steps})
        worst_priority = min(s["priority"] for s in quhe_steps)
        bad_sources = sorted({s["source"] for s in quhe_steps if s.get("source_status") == "bad"})
        out.append({
            "type": "collect_quhe",
            "exchange": "ALL",
            "kind": ",".join(kinds),
            "source": "quheqihuo/official-fallback",
            "source_status": "bad" if bad_sources else "mixed",
            "priority": worst_priority,
            "endpoint": quhe_steps[0]["endpoint"],
            "reason": f"增强数据缺口涉及 {len(exchanges)} 个交易所：{'、'.join(exchanges[:6])}",
            "expected_effect": "一次刷新资金流、基差、仓单、合约树、历史持仓和席位 fallback",
            "risk": "第三方增强源可能返回空；执行后用 coverage diff 判断是否改善。",
            "children": quhe_steps,
        })
    return out


def skip_item(exchange: str, kind: str, cell: dict[str, Any], reason_code: str) -> dict[str, Any]:
    reason = cell.get("message") or "不建议自动重试"
    if reason_code == "archive_dependency":
        reason = "席位归档来自外部结构化归档/历史资产，不能通过普通采集直接补齐。"
    return {
        "exchange": exchange,
        "kind": kind,
        "status": cell.get("status"),
        "reason_code": reason_code,
        "reason": reason,
    }


def recommended_source(exchange: str, kind: str) -> str:
    if exchange == "DCE" and kind == "daily":
        return "dce_sina_fallback"
    return "akshare"


def enhancement_source(kind: str) -> str:
    if kind == "warehouse_receipt":
        return "quheqihuo/akshare_official"
    if kind == "basis":
        return "quheqihuo/akshare_100ppi"
    return "quheqihuo"


def risk_note(source: str, status: str, exchange: str, kind: str) -> str:
    if exchange == "DCE" and kind == "seat_rank":
        return "DCE 席位公开源长期不稳定，重试可能仍失败；需要商业授权源兜底。"
    if status == "bad":
        return f"推荐源 {source} 当前健康较差，建议执行后检查 raw archive 和 coverage diff。"
    return "低风险：只做采集/补采，不伪造缺失数据。"


def plan_summary(steps: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    core_steps = sum(1 for s in steps if s.get("type") == "recollect")
    enhancement_steps = sum(1 for s in steps if s.get("type") == "collect_quhe")
    return {
        "steps": len(steps),
        "core_steps": core_steps,
        "enhancement_steps": enhancement_steps,
        "skipped": len(skipped),
        "summary": f"建议执行 {len(steps)} 个步骤：核心补采 {core_steps} 个，增强源刷新 {enhancement_steps} 个；跳过 {len(skipped)} 个不可自动处理项。",
    }
