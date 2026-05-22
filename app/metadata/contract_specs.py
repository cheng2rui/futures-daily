from __future__ import annotations

# Contract point value / multiplier mapping, migrated from futures-panel.
# value means RMB per 1 price point per lot.

POINT_VALUE = {
    # 上海期货交易所（SHFE）
    "AU": 1000, "AG": 15,   "CU": 5,   "AL": 5,    "ZN": 5,    "PB": 5,
    "NI": 1,    "SN": 1,    "RB": 10,  "HC": 10,  "WR": 10,  "SS": 5,
    "RU": 10,   "FU": 10,  "BU": 10,  "SP": 10,  "AO": 20,  "AD": 10,
    "OP": 40,   "BR": 5,   "SC": 100,
    # 大连商品交易所（DCE）
    "I": 100,   "JM": 60,   "J": 100,  "M": 10,   "Y": 10,   "P": 10,
    "A": 10,    "B": 10,   "C": 10,   "CS": 10,  "L": 5,    "V": 5,
    "PP": 5,    "PE": 5,   "PG": 20,  "EB": 5,   "EG": 10,  "LH": 16,
    "JD": 10,   "RR": 10,  "FB": 10,  "BB": 500, "LG": 90,   "BZ": 30,
    # 郑州商品交易所（CZCE）
    "SR": 10,   "CF": 5,    "TA": 5,   "MA": 10,  "RM": 10,  "OI": 10,
    "PK": 5,    "FG": 20,  "WH": 20,  "PM": 50,  "ZC": 100, "SA": 20,
    "RI": 20,   "JR": 20,  "LR": 20,  "RS": 10,  "SF": 5,   "SM": 5,
    "AP": 10,   "CJ": 5,   "CY": 5,   "PF": 5,   "UR": 20,  "SH": 30,
    "PX": 5,    "PR": 15,  "PL": 20,
    # 国际能源/广州期货交易所
    "BC": 5,    "NR": 10,  "EC": 10,  "LU": 10,
    "SI": 5,    "LC": 1,   "PS": 3,   "PT": 1000, "PD": 1000,
    # 金融期货（中金所）
    "IF": 300,  "IH": 300,  "IC": 200,  "IM": 200,
    "TL": 10000,"TF": 10000,"T": 10000, "TS": 20000,
}

# ─────────────────────────────────────────────
# MARGIN_RATE：各品种保证金率（期货公司通常在交易所标准上加 2-3%）
# key =品种代码 prefix，value = 保证金率（小数，如 0.08 = 8%）
# 来源：各交易所公告 + 期货公司惯例，参考 Vibe-Trading china_futures.py
# ─────────────────────────────────────────────


def get_point_value(symbol: str) -> float | None:
    return POINT_VALUE.get((symbol or "").upper())
