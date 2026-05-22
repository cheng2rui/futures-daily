from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metadata.source_capabilities import (
    classify_archive_capability,
    classify_external_capability,
    is_cold_or_inactive,
    is_third_party_empty,
)
from app.models import DailyBar, QuheContract, SeatRankRow, VarietyDailyFact


def build_gap_analysis(db: Session, trade_date: str) -> dict[str, Any]:
    facts = list(db.scalars(select(VarietyDailyFact).where(VarietyDailyFact.trade_date == trade_date)))
    bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date == trade_date)))
    seats = list(db.scalars(select(SeatRankRow).where(SeatRankRow.trade_date == trade_date)))
    quhe_contracts = list(db.scalars(select(QuheContract).where(QuheContract.is_main == True)))  # noqa: E712

    daily_symbols = {(b.exchange, b.symbol.upper()) for b in bars}
    seat_symbols = {(s.exchange, s.variety.upper()) for s in seats}
    quhe_symbols_by_exchange: dict[str, set[str]] = defaultdict(set)
    for c in quhe_contracts:
        exchange = board_to_exchange(c.board_name)
        if exchange:
            quhe_symbols_by_exchange[exchange].add((c.symbol or c.product_code or "").upper())

    gaps = []
    for fact in facts:
        symbol = fact.symbol.upper()
        exchange = fact.exchange
        if fact.quality_daily != "ok":
            gaps.append(gap_item(trade_date, exchange, symbol, fact.name, "daily", classify_daily(exchange, symbol, daily_symbols)))
        if fact.quality_seat_rank != "ok":
            gaps.append(gap_item(trade_date, exchange, symbol, fact.name, "seat_rank", classify_seat(exchange, symbol, seat_symbols, quhe_symbols_by_exchange)))
        if fact.quality_archive_signal != "ok":
            gaps.append(gap_item(trade_date, exchange, symbol, fact.name, "archive_signal", classify_archive(exchange, symbol)))
        parsed = parse_json(fact.fact_json)
        ext = parsed.get("external_signals", {}) if isinstance(parsed, dict) else {}
        for kind, label in [
            ("capital_flow", "capital_flow"),
            ("basis", "basis"),
            ("warehouse_receipt", "warehouse_receipt"),
            ("history_holding", "history_holding"),
        ]:
            if not ext.get(kind):
                gaps.append(gap_item(trade_date, exchange, symbol, fact.name, label, classify_external(exchange, symbol, kind)))

    summary = defaultdict(int)
    by_exchange: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in gaps:
        summary[g["reason_code"]] += 1
        by_exchange[g["exchange"]][g["reason_code"]] += 1

    actionable_count = sum(1 for g in gaps if g.get("actionable"))

    return {
        "trade_date": trade_date,
        "count": len(gaps),
        "actionable_count": actionable_count,
        "explained_count": len(gaps) - actionable_count,
        "summary": dict(sorted(summary.items())),
        "by_exchange": {k: dict(sorted(v.items())) for k, v in sorted(by_exchange.items())},
        "gaps": gaps,
    }


def gap_item(trade_date: str, exchange: str, symbol: str, name: str, kind: str, reason: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "exchange": exchange,
        "symbol": symbol,
        "name": name,
        "kind": kind,
        **reason,
    }


def classify_daily(exchange: str, symbol: str, daily_symbols: set[tuple[str, str]]) -> dict[str, Any]:
    if (exchange, symbol) not in daily_symbols:
        return reason("daily_not_collected", "日行情未入库；需要检查交易所日行情 adapter。", True)
    return reason("unknown_daily_gap", "日行情存在但 fact 标记缺失；可能是 materialize 逻辑问题。", True)


def classify_seat(exchange: str, symbol: str, seat_symbols: set[tuple[str, str]], quhe_symbols_by_exchange: dict[str, set[str]]) -> dict[str, Any]:
    if (exchange, symbol) in seat_symbols:
        return reason("materialize_mapping_issue", "席位表已有数据但 fact 未匹配；优先检查 symbol/variety 映射。", True)
    if is_cold_or_inactive(exchange, symbol):
        return reason("inactive_or_illiquid", "冷门/停用/低流动性品种，交易所或第三方通常无席位披露。", False)
    if symbol not in quhe_symbols_by_exchange.get(exchange, set()):
        return reason("third_party_mapping_missing", "曲合合约树没有该品种主力映射；需要补映射或换源。", True)
    if is_third_party_empty(exchange, symbol):
        return reason("third_party_empty", "曲合接口探测为空，短期可能无法通过该源补齐。", False)
    return reason("fallback_untried_or_empty", "官方/AkShare 缺失；第三方 fallback 未命中或返回空，可继续定向探测。", True)


def classify_archive(exchange: str, symbol: str) -> dict[str, Any]:
    capability = classify_archive_capability(exchange, symbol)
    if capability:
        return capability.as_dict()
    return reason("archive_mapping_or_source_gap", "结构化归档未匹配；可能是名称映射差异或源归档缺该品种。", True)


def classify_external(exchange: str, symbol: str, kind: str) -> dict[str, Any]:
    capability = classify_external_capability(exchange, symbol, kind)
    if capability:
        return capability.as_dict()
    return reason("external_source_gap", f"曲合 {kind} 未覆盖该品种，可继续寻找其他备用源。", True)


def reason(code: str, text: str, actionable: bool) -> dict[str, Any]:
    return {"reason_code": code, "reason": text, "actionable": actionable}


def board_to_exchange(board_name: str | None) -> str:
    return {
        "上海期货交易所": "SHFE",
        "大连商品交易所": "DCE",
        "郑州商品交易所": "CZCE",
        "中国金融期货交易所": "CFFEX",
        "上海国际能源交易中心": "INE",
        "上期能源": "INE",
        "广州期货交易所": "GFEX",
    }.get(board_name or "", "")


def parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}
