from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.metadata.variety_meta import get_variety_name
from app.models import DailyBar
from app.services.structure import pct_change, sector_for


def build_term_structure(bars: list[DailyBar], limit: int = 12) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[DailyBar]] = defaultdict(list)
    for bar in bars:
        if bar.close is None:
            continue
        grouped[(str(bar.exchange or "").upper(), str(bar.symbol or "").upper())].append(bar)

    items: list[dict[str, Any]] = []
    for (exchange, symbol), rows in grouped.items():
        curve = sorted([curve_point(x) for x in rows], key=lambda x: (x["sort_key"], -float(x.get("open_interest") or 0)))
        if len(curve) < 2:
            continue
        liquid = sorted(curve, key=lambda x: (float(x.get("volume") or 0) * 0.65 + float(x.get("open_interest") or 0) * 0.35), reverse=True)
        main = liquid[0]
        second = next((x for x in liquid[1:] if x["contract"] != main["contract"]), None)
        near = curve[0]
        far = curve[-1]
        main_second_spread = spread(main, second)
        near_far_spread = spread(near, far)
        structure_type = classify_structure(curve)
        item = {
            "exchange": exchange,
            "symbol": symbol,
            "name": get_variety_name(symbol),
            "sector": sector_for(symbol),
            "main_contract": display_contract(main["contract"]),
            "second_contract": display_contract(second["contract"]) if second else "",
            "near_contract": display_contract(near["contract"]),
            "far_contract": display_contract(far["contract"]),
            "main_second_spread": main_second_spread,
            "near_far_spread": near_far_spread,
            "structure_type": structure_type,
            "curve_points": [{**{k: v for k, v in x.items() if k != "sort_key"}, "contract": display_contract(x.get("contract"))} for x in curve[:16]],
            "signal_strength": signal_strength(main_second_spread, near_far_spread, curve),
        }
        item["summary"] = summarize_item(item)
        items.append(item)

    items.sort(key=lambda x: x.get("signal_strength") or 0, reverse=True)
    return {
        "count": len(items),
        "items": items[:limit],
        "summary": summarize_digest(items),
    }


def curve_point(bar: DailyBar) -> dict[str, Any]:
    return {
        "contract": bar.contract,
        "close": bar.close,
        "settlement": bar.settlement,
        "change_pct": round(pct_change(bar), 2) if pct_change(bar) is not None else None,
        "volume": bar.volume,
        "open_interest": bar.open_interest,
        "sort_key": contract_sort_key(bar.contract),
    }


def contract_sort_key(contract: str) -> tuple[int, str]:
    text = str(contract or "").upper()
    m = re.search(r"(\d{3,4})", text)
    if not m:
        return (999999, text)
    raw = m.group(1)
    if len(raw) == 3:
        year = 2020 + int(raw[0])
        month = int(raw[1:])
    else:
        yy = int(raw[:2])
        year = 2000 + yy if yy >= 20 else 2100 + yy
        month = int(raw[2:])
    if month < 1 or month > 12:
        return (999999, text)
    return (year * 100 + month, text)


def display_contract(contract: str | None) -> str:
    text = str(contract or "").upper()
    return re.sub(r"^([A-Z_]+)(\d{3})$", lambda m: f"{m.group(1)}2{m.group(2)}", text)


def spread(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any] | None:
    if not left or not right or left.get("close") is None or right.get("close") is None:
        return None
    value = round(float(left["close"]) - float(right["close"]), 4)
    base = float(right["close"] or 0)
    pct = round(value / base * 100, 2) if base else None
    return {"left": display_contract(left.get("contract")), "right": display_contract(right.get("contract")), "value": value, "pct": pct}


def classify_structure(curve: list[dict[str, Any]]) -> str:
    prices = [float(x["close"]) for x in curve if x.get("close") is not None]
    if len(prices) < 2:
        return "unknown"
    up = sum(1 for a, b in zip(prices, prices[1:]) if b > a)
    down = sum(1 for a, b in zip(prices, prices[1:]) if b < a)
    total = len(prices) - 1
    if up / total >= 0.7:
        return "contango"
    if down / total >= 0.7:
        return "backwardation"
    return "mixed"


def signal_strength(main_second: dict[str, Any] | None, near_far: dict[str, Any] | None, curve: list[dict[str, Any]]) -> float:
    parts = []
    for item in [main_second, near_far]:
        if item and item.get("pct") is not None:
            parts.append(abs(float(item["pct"])))
    changes = [abs(float(x.get("change_pct") or 0)) for x in curve]
    if changes:
        parts.append(max(changes))
    return round(sum(parts), 2)


def summarize_item(item: dict[str, Any]) -> str:
    label = {"contango": "升水结构", "backwardation": "贴水结构", "mixed": "混合结构", "unknown": "结构不明"}.get(item.get("structure_type"), "结构不明")
    nf = item.get("near_far_spread") or {}
    ms = item.get("main_second_spread") or {}
    bits = [label]
    if ms:
        bits.append(f"主次价差 {ms.get('value')}({ms.get('pct')}%)")
    if nf:
        bits.append(f"近远月价差 {nf.get('value')}({nf.get('pct')}%)")
    return "；".join(bits)


def summarize_digest(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无足够合约曲线数据。"
    top = items[:3]
    return "；".join(f"{x.get('name') or x.get('symbol')} {x.get('symbol')} {x.get('summary')}" for x in top)
