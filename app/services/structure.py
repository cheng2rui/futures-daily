from __future__ import annotations

from collections import defaultdict

from app.models import DailyBar

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


def pct_change(row: DailyBar) -> float | None:
    base = row.pre_close or row.settlement
    if not base or not row.close:
        return None
    return (row.close - base) / base * 100


def build_structure(bars: list[DailyBar]) -> dict:
    buckets = {"price_up_oi_up": [], "price_up_oi_down": [], "price_down_oi_up": [], "price_down_oi_down": []}
    sector_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "up": 0, "down": 0, "volume": 0.0, "open_interest": 0.0})

    for bar in bars:
        chg = pct_change(bar)
        oi = bar.open_interest or 0
        sector = sector_for(bar.symbol)
        sector_stats[sector]["count"] += 1
        sector_stats[sector]["volume"] += bar.volume or 0
        sector_stats[sector]["open_interest"] += oi
        if chg is not None and chg > 0:
            sector_stats[sector]["up"] += 1
        if chg is not None and chg < 0:
            sector_stats[sector]["down"] += 1
        if chg is None:
            continue
        item = {"exchange": bar.exchange, "symbol": bar.symbol, "contract": bar.contract, "change_pct": round(chg, 2), "open_interest": oi, "volume": bar.volume}
        if chg > 0 and oi > 0:
            buckets["price_up_oi_up"].append(item)
        elif chg > 0:
            buckets["price_up_oi_down"].append(item)
        elif chg < 0 and oi > 0:
            buckets["price_down_oi_up"].append(item)
        elif chg < 0:
            buckets["price_down_oi_down"].append(item)

    for key in buckets:
        buckets[key] = sorted(buckets[key], key=lambda x: abs(x.get("change_pct") or 0), reverse=True)[:10]

    sectors = []
    for name, s in sector_stats.items():
        sectors.append({
            "name": name,
            "count": s["count"],
            "up": s["up"],
            "down": s["down"],
            "up_ratio": round(s["up"] / s["count"] * 100, 1) if s["count"] else 0,
            "volume": round(s["volume"], 2),
            "open_interest": round(s["open_interest"], 2),
        })
    sectors.sort(key=lambda x: (x["up_ratio"], x["count"]), reverse=True)
    return {"quadrants": buckets, "sector_breadth": sectors}
