from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.metadata.variety_meta import get_variety_name


SECTOR_MAP = {
    "黑色": {"RB", "HC", "I", "J", "JM", "SF", "SM", "SS"},
    "有色": {"CU", "AL", "ZN", "PB", "NI", "SN", "AO", "BC"},
    "化工": {"TA", "PX", "EG", "MA", "PP", "L", "V", "RU", "NR", "BU", "FU", "LU", "PF", "SA", "UR", "FG", "BR"},
    "农产品": {"A", "B", "M", "Y", "P", "C", "CS", "JD", "LH", "CF", "SR", "OI", "RM", "AP", "CJ", "PK"},
    "能源": {"SC", "LU", "FU", "BU", "PG", "EC"},
    "贵金属": {"AU", "AG"},
    "金融期货": {"IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"},
    "广期所重点": {"SI", "LC", "PS"},
}


def sector_for(symbol: str) -> str:
    symbol = (symbol or "").upper()
    for sector, symbols in SECTOR_MAP.items():
        if symbol in symbols:
            return sector
    return "其他"


INDUSTRY_CHAINS: dict[str, dict[str, Any]] = {
    "black": {
        "name": "黑色建材",
        "symbols": ["I", "J", "JM", "RB", "HC", "SS", "SF", "SM", "FG", "SA"],
        "upstream": ["I", "J", "JM", "SF", "SM"],
        "midstream": ["RB", "HC", "SS"],
        "downstream": ["FG", "SA"],
    },
    "energy_chemical": {
        "name": "能化链",
        "symbols": ["SC", "FU", "LU", "BU", "PG", "TA", "PX", "PF", "PR", "EG", "MA", "L", "PP", "V", "EB", "BZ", "BR", "UR", "SH"],
        "upstream": ["SC", "FU", "LU", "PG", "PX", "BZ"],
        "midstream": ["TA", "EG", "MA", "L", "PP", "V", "EB", "BR", "SH"],
        "downstream": ["PF", "PR", "BU", "UR"],
    },
    "oils_oilseeds": {
        "name": "油脂油料",
        "symbols": ["A", "B", "M", "Y", "P", "RM", "OI", "RS", "PK"],
        "upstream": ["A", "B", "RS", "PK"],
        "midstream": ["M", "RM", "Y", "OI", "P"],
        "downstream": [],
    },
    "agriculture": {
        "name": "农副产品",
        "symbols": ["C", "CS", "JD", "LH", "CF", "CY", "SR", "AP", "CJ", "WH", "PM", "RI", "LR", "JR", "RR"],
        "upstream": ["C", "CF", "SR", "WH", "PM", "RI", "LR", "JR"],
        "midstream": ["CS", "CY", "RR"],
        "downstream": ["JD", "LH", "AP", "CJ"],
    },
    "nonferrous": {
        "name": "有色金属",
        "symbols": ["CU", "BC", "AL", "AO", "ZN", "PB", "NI", "SN", "LC", "SI", "AD"],
        "upstream": ["BC", "AO", "SI", "LC"],
        "midstream": ["CU", "AL", "ZN", "PB", "NI", "SN", "AD"],
        "downstream": [],
    },
    "precious": {
        "name": "贵金属",
        "symbols": ["AU", "AG", "PT", "PD"],
        "upstream": [],
        "midstream": ["AU", "AG", "PT", "PD"],
        "downstream": [],
    },
    "softs_forest": {
        "name": "软商品/林纸",
        "symbols": ["RU", "NR", "SP", "OP", "LG", "FB", "BB"],
        "upstream": ["RU", "NR", "LG"],
        "midstream": ["SP", "FB", "BB"],
        "downstream": ["OP"],
    },
    "financial": {
        "name": "金融期货",
        "symbols": ["IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"],
        "upstream": [],
        "midstream": ["IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"],
        "downstream": [],
    },
}

SYMBOL_TO_CHAIN: dict[str, str] = {
    symbol: chain_id
    for chain_id, chain in INDUSTRY_CHAINS.items()
    for symbol in chain["symbols"]
}


def build_industry_chain_digest(dataset: dict, abnormal_cards: list[dict] | None = None, limit: int = 8) -> dict[str, Any]:
    rows_by_symbol: dict[str, dict] = {}
    for row in dataset.get("rows", []) or []:
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            rows_by_symbol[symbol] = row

    abnormal_by_symbol = {str(card.get("symbol") or "").upper(): card for card in abnormal_cards or []}
    chains: list[dict[str, Any]] = []
    for chain_id, chain in INDUSTRY_CHAINS.items():
        symbols = [s for s in chain["symbols"] if s in rows_by_symbol]
        if not symbols:
            continue
        members = [member_item(symbol, rows_by_symbol[symbol], abnormal_by_symbol.get(symbol), chain) for symbol in symbols]
        valid_changes = [float(x["change_pct"]) for x in members if x.get("change_pct") is not None]
        up = sum(1 for x in valid_changes if x > 0)
        down = sum(1 for x in valid_changes if x < 0)
        avg_change = round(sum(valid_changes) / len(valid_changes), 2) if valid_changes else None
        volume = sum(float(x.get("volume") or 0) for x in members)
        open_interest = sum(float(x.get("open_interest") or 0) for x in members)
        abnormal_count = sum(1 for x in members if x.get("abnormal_score"))
        divergence = calc_divergence(valid_changes)
        leading = sorted(members, key=member_strength, reverse=True)[:5]
        direction = classify_direction(avg_change, up, down, len(valid_changes))
        score = round(abs(avg_change or 0) * 3 + divergence * 2 + abnormal_count * 3 + min(volume / 5_000_000, 8), 2)
        chain_item = {
            "id": chain_id,
            "name": chain["name"],
            "symbols": symbols,
            "count": len(symbols),
            "up": up,
            "down": down,
            "avg_change": avg_change,
            "direction": direction,
            "divergence_score": round(divergence, 2),
            "abnormal_count": abnormal_count,
            "volume": round(volume, 2),
            "open_interest": round(open_interest, 2),
            "leading_symbols": leading,
            "divergence_symbols": pick_divergence_symbols(members, avg_change),
            "summary": "",
            "score": score,
        }
        chain_item["summary"] = summarize_chain(chain_item)
        chains.append(chain_item)

    chains.sort(key=lambda x: x.get("score") or 0, reverse=True)
    top = chains[:limit]
    return {
        "count": len(chains),
        "items": top,
        "summary": summarize_digest(top),
        "coverage": {"mapped_symbols": len(rows_by_symbol), "chains": len(chains)},
    }


def member_item(symbol: str, row: dict, abnormal: dict | None, chain: dict) -> dict[str, Any]:
    role = "相关"
    if symbol in chain.get("upstream", []):
        role = "上游"
    elif symbol in chain.get("midstream", []):
        role = "中游"
    elif symbol in chain.get("downstream", []):
        role = "下游"
    return {
        "symbol": symbol,
        "name": row.get("name") or get_variety_name(symbol),
        "role": role,
        "sector": row.get("sector") or sector_for(symbol),
        "main_contract": row.get("main_contract"),
        "change_pct": safe_round(row.get("main_change_pct")),
        "volume": row.get("total_volume") or row.get("main_volume"),
        "open_interest": row.get("total_open_interest") or row.get("main_open_interest"),
        "abnormal_score": safe_round((abnormal or {}).get("score")),
        "signal": (abnormal or {}).get("signal"),
        "bias": (abnormal or {}).get("bias"),
    }


def member_strength(item: dict) -> float:
    return abs(float(item.get("change_pct") or 0)) * 2 + float(item.get("abnormal_score") or 0) + min(float(item.get("volume") or 0) / 1_000_000, 5)


def calc_divergence(changes: list[float]) -> float:
    if len(changes) < 2:
        return 0.0
    pos = sum(1 for x in changes if x > 0)
    neg = sum(1 for x in changes if x < 0)
    if not pos or not neg:
        return 0.0
    spread = max(changes) - min(changes)
    balance = min(pos, neg) / max(pos, neg)
    return round(spread * balance, 2)


def pick_divergence_symbols(members: list[dict], avg_change: float | None) -> list[dict]:
    if avg_change is None:
        return []
    out = []
    for item in members:
        chg = item.get("change_pct")
        if chg is None:
            continue
        if avg_change > 0 and chg < -0.3 or avg_change < 0 and chg > 0.3 or abs(float(chg) - avg_change) >= 2.0:
            out.append(item)
    out.sort(key=lambda x: abs(float(x.get("change_pct") or 0) - avg_change), reverse=True)
    return out[:4]


def classify_direction(avg_change: float | None, up: int, down: int, total: int) -> str:
    if avg_change is None or not total:
        return "unknown"
    if up / total >= 0.65 and avg_change > 0:
        return "strong"
    if down / total >= 0.65 and avg_change < 0:
        return "weak"
    return "divergent"


def summarize_chain(item: dict) -> str:
    direction_label = {"strong": "链条偏强", "weak": "链条偏弱", "divergent": "链条分化", "unknown": "链条信号不足"}.get(item.get("direction"), "链条信号不足")
    bits = [f"{direction_label}，均涨跌 {fmt_pct(item.get('avg_change'))}"]
    if item.get("abnormal_count"):
        bits.append(f"{item.get('abnormal_count')} 个品种进入异动观察")
    if item.get("divergence_score"):
        names = "、".join(x.get("name") or x.get("symbol") for x in item.get("divergence_symbols") or [])
        bits.append(f"存在背离{f'：{names}' if names else ''}")
    lead = "、".join(f"{x.get('name') or x.get('symbol')}({fmt_pct(x.get('change_pct'))})" for x in (item.get("leading_symbols") or [])[:3])
    if lead:
        bits.append(f"核心变化：{lead}")
    return "；".join(bits)


def summarize_digest(items: list[dict]) -> str:
    if not items:
        return "暂无足够产业链数据。"
    return "；".join(f"{x.get('name')}：{x.get('summary')}" for x in items[:3])


def fmt_pct(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)


def safe_round(value, digits: int = 2):
    try:
        if value is None or value == "":
            return None
        return round(float(value), digits)
    except Exception:
        return None
