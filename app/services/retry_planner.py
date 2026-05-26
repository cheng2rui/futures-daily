from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.coverage_matrix import build_coverage_matrix
from app.services.error_classifier import classify_record_error
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
                item = core_step(trade_date, exchange, kind, cell, health_by_source)
                (steps if item.get("executable") else skipped).append(item)
            elif kind in ENHANCEMENT_KINDS:
                item = enhancement_step(trade_date, exchange, kind, cell, health_by_source)
                (steps if item.get("executable") else skipped).append(item)
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
    category = step_error_category(source_health, cell, kind, source)
    decision = planner_decision(category, kind, status)
    priority = 10 if kind == "daily" else 20
    if cell.get("status") == "failed":
        priority -= 3
    if status == "bad":
        priority += 6
    priority += int(decision.get("priority_delta") or 0)
    step = {
        "type": "recollect",
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "source_status": status,
        "priority": priority,
        "executable": bool(decision["executable"]),
        "decision": decision["action"],
        "decision_label": decision["label"],
        "error_category": category,
        "endpoint": f"POST /api/reports/{trade_date}/recollect?exchange={exchange}&kinds={kind}&rebuild=true",
        "reason": f"{exchange} {kind} 当前 {cell.get('status')}：{cell.get('message') or '数据缺失'}",
        "expected_effect": decision.get("expected_effect") or ("补齐核心覆盖并刷新日报" if kind == "daily" else "补齐席位覆盖；若源不可用会保留 data_gap"),
        "risk": decision.get("risk") or risk_note(source, status, exchange, kind),
        "reason_code": decision.get("reason_code", "retryable"),
    }
    browser = browser_probe_hint(exchange, kind, category, cell)
    if browser:
        step["browser_probe"] = browser
    return step


def enhancement_step(trade_date: str, exchange: str, kind: str, cell: dict[str, Any], health_by_source: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = enhancement_source(kind)
    source_health = health_by_source.get(source) or {}
    status = source_health.get("status") or "unknown"
    category = step_error_category(source_health, cell, kind, source)
    decision = planner_decision(category, kind, status)
    priority = 40 if kind == "capital_flow" else 45
    if status == "bad":
        priority += 8
    priority += int(decision.get("priority_delta") or 0)
    return {
        "type": "collect_quhe",
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "source_status": status,
        "priority": priority,
        "executable": bool(decision["executable"]),
        "decision": decision["action"],
        "decision_label": decision["label"],
        "error_category": category,
        "endpoint": f"POST /api/dataset/collect-quhe/{trade_date}",
        "reason": f"{exchange} {kind} 当前 {cell.get('status')}：{cell.get('message') or '增强数据缺失'}",
        "expected_effect": decision.get("expected_effect") or "刷新曲合/官方增强数据后重新物化数据集",
        "risk": decision.get("risk") or risk_note(source, status, exchange, kind),
        "reason_code": decision.get("reason_code", "retryable"),
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
            "executable": True,
            "decision": "retry_enhancement_bundle",
            "decision_label": "刷新增强源包",
            "error_category": summarize_child_categories(quhe_steps),
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
    category = classify_record_error(message=reason, status=cell.get("status"), kind=kind)
    source = recommended_source(exchange, kind) if kind in CORE_KINDS else enhancement_source(kind) if kind in ENHANCEMENT_KINDS else "archive"
    return {
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "status": cell.get("status"),
        "reason_code": reason_code,
        "reason": reason,
        "executable": False,
        "decision": reason_code,
        "decision_label": skip_label(reason_code),
        "error_category": category,
        "diagnostic_hint": skip_diagnostic_hint(reason_code, category),
    }


def recommended_source(exchange: str, kind: str) -> str:
    if exchange == "DCE" and kind == "daily":
        return "dce_sina_fallback"
    return "akshare"


def browser_probe_hint(exchange: str, kind: str, category: dict[str, Any], cell: dict[str, Any]) -> dict[str, Any] | None:
    """Describe the optional CloakBrowser official-page probe for seat gaps.

    v0.5.13 only wires the infrastructure and planner hint. The browser adapter
    must still archive raw official responses before parser replay promotes data.
    """
    if kind != "seat_rank" or exchange == "INE":
        return None
    cfg = get_settings().browser
    if not cfg.enabled or cfg.provider != "cloakbrowser":
        return None
    code = category.get("code") or "unknown"
    if code not in {"anti_bot", "timeout", "network", "empty", "missing_without_error", "unknown"} and cell.get("status") not in {"missing", "failed", "partial"}:
        return None
    return {
        "available": True,
        "source": f"{exchange.lower()}_official_cloakbrowser",
        "provider": "cloakbrowser",
        "label": "CloakBrowser 官方页低频探测",
        "stage": "v0.5.13 infrastructure",
        "python_path": cfg.python_path,
        "binary_path": cfg.binary_path,
        "reason": "常规席位源缺失/失败时，可用 CloakBrowser 抓取官方页面原始响应，先写 raw_archive，再做 parser replay。",
        "next_step": "实现对应 exchange browser source adapter 后再加入 Retry Runner 自动执行。",
    }


def enhancement_source(kind: str) -> str:
    if kind == "warehouse_receipt":
        return "quheqihuo/akshare_official"
    if kind == "basis":
        return "quheqihuo/akshare_100ppi"
    return "quheqihuo"


def step_error_category(source_health: dict[str, Any], cell: dict[str, Any], kind: str, source: str) -> dict[str, Any]:
    latest = source_health.get("latest_error_category") if isinstance(source_health.get("latest_error_category"), dict) else None
    if latest and latest.get("code") not in {"unknown", "missing_without_error"}:
        return latest
    return classify_record_error(message=cell.get("message"), status=cell.get("status"), kind=kind, source=source)


def planner_decision(category: dict[str, Any], kind: str, source_status: str) -> dict[str, Any]:
    code = category.get("code") or "unknown"
    if code in {"adapter_not_supported", "auth"}:
        return {
            "executable": False,
            "action": "connect_authorized_source" if code == "auth" else "connect_adapter",
            "label": "接入授权源" if code == "auth" else "补 adapter",
            "reason_code": code,
            "expected_effect": "当前不能靠重试解决，需要补凭证/授权源或 adapter。",
            "risk": category.get("suggestion") or "不执行自动重试，避免无效请求。",
        }
    if code == "parser":
        return {
            "executable": False,
            "action": "parser_replay",
            "label": "先做 Parser Replay",
            "reason_code": "parser_replay",
            "expected_effect": "先用 raw archive 重放定位字段变化，再修 parser。",
            "risk": "直接重采大概率仍失败；应先修解析。",
        }
    if code == "anti_bot":
        return {
            "executable": True,
            "action": "retry_with_backoff",
            "label": "低频重试",
            "priority_delta": 8,
            "expected_effect": "低频补采并保留 raw archive；若仍触发反爬，转授权源/浏览器会话。",
            "risk": category.get("suggestion") or "可能继续触发频控。",
        }
    if code in {"timeout", "network"}:
        return {
            "executable": True,
            "action": "retry_network",
            "label": "网络重试",
            "priority_delta": -2,
            "expected_effect": "网络类错误通常可重试恢复。",
            "risk": category.get("suggestion") or "若连续失败需检查网络/代理/DNS。",
        }
    if code == "empty":
        return {
            "executable": True,
            "action": "retry_verify_params",
            "label": "校验参数后重试",
            "priority_delta": 4,
            "expected_effect": "再次采集并验证交易日/参数/品种映射是否导致空返回。",
            "risk": category.get("suggestion") or "若源当天确无披露，重试不会改善。",
        }
    return {
        "executable": True,
        "action": "retry",
        "label": "普通重试",
        "priority_delta": 3 if source_status == "bad" else 0,
        "expected_effect": "重新采集并用 coverage diff 判断是否改善。",
        "risk": "错误信息不足，重试后需检查 raw archive 和 latest_run。",
    }


def summarize_child_categories(children: list[dict[str, Any]]) -> dict[str, Any]:
    categories = [c.get("error_category") or {} for c in children]
    actionable = [c for c in categories if c.get("code") not in {"unknown", "missing_without_error", None}]
    return (actionable or categories or [{}])[0]


def skip_label(reason_code: str) -> str:
    return {
        "not_supported": "跳过：不适用",
        "archive_dependency": "跳过：依赖归档",
        "adapter_not_supported": "跳过：补 adapter",
        "auth": "跳过：需授权",
        "parser_replay": "跳过：先 replay",
    }.get(reason_code, "跳过")


def skip_diagnostic_hint(reason_code: str, category: dict[str, Any]) -> str:
    if reason_code == "not_supported":
        return "当前交易所/数据类型没有可用采集 adapter；需要接入新源或授权源。"
    if reason_code == "archive_dependency":
        return "此项依赖外部归档文件，优先检查归档路径、index.json 和 parser replay。"
    if reason_code == "parser_replay":
        return "直接重试可能继续失败，先用 raw archive replay 定位字段变化。"
    if reason_code in {"adapter_not_supported", "auth"}:
        return category.get("suggestion") or "需要先补 adapter、凭证或授权源。"
    return category.get("suggestion") or "查看 source health、raw archive 和最近任务记录。"


def skipped_breakdown(skipped: list[dict[str, Any]]) -> dict[str, Any]:
    by_reason: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    samples: list[str] = []
    for item in skipped:
        reason_code = item.get("reason_code") or "unknown"
        kind = item.get("kind") or "unknown"
        by_reason[reason_code] = by_reason.get(reason_code, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if len(samples) < 5:
            label = item.get("decision_label") or skip_label(reason_code)
            samples.append(f"{item.get('exchange') or '-'} {kind}：{label}")
    return {"by_reason": by_reason, "by_kind": by_kind, "samples": samples}


def risk_note(source: str, status: str, exchange: str, kind: str) -> str:
    if exchange == "DCE" and kind == "seat_rank":
        return "DCE 席位公开源长期不稳定，重试可能仍失败；后续优先用 CloakBrowser 官方页低频探测或商业授权源兜底。"
    if status == "bad":
        return f"推荐源 {source} 当前健康较差，建议执行后检查 raw archive 和 coverage diff。"
    return "低风险：只做采集/补采，不伪造缺失数据。"


def plan_summary(steps: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    core_steps = sum(1 for s in steps if s.get("type") == "recollect")
    enhancement_steps = sum(1 for s in steps if s.get("type") == "collect_quhe")
    skip_info = skipped_breakdown(skipped)
    skipped_text = f"；跳过 {len(skipped)} 个不可自动处理项。"
    if skipped:
        samples = "、".join(skip_info["samples"])
        skipped_text = f"；跳过 {len(skipped)} 个不可自动处理项（{samples}）。"
    return {
        "steps": len(steps),
        "core_steps": core_steps,
        "enhancement_steps": enhancement_steps,
        "skipped": len(skipped),
        "skipped_by_reason": skip_info["by_reason"],
        "skipped_by_kind": skip_info["by_kind"],
        "skipped_samples": skip_info["samples"],
        "summary": f"建议执行 {len(steps)} 个步骤：核心补采 {core_steps} 个，增强源刷新 {enhancement_steps} 个{skipped_text}",
    }
