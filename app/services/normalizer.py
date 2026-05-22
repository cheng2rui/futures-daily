from __future__ import annotations

import re
from typing import Any


def parse_variety(contract: str | None) -> str:
    if not contract:
        return ""
    m = re.match(r"([A-Za-z]+)", str(contract))
    return m.group(1).upper() if m else str(contract).upper()


def pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in ("", None):
            return row[name]
    return None


def as_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def normalize_daily_row(exchange: str, row: dict[str, Any]) -> dict[str, Any]:
    # Prefer explicit contract when fallback sources provide both variety symbol and continuous contract code.
    contract = str(pick(row, "contract", "合约", "合约代码", "symbol") or "")
    symbol = str(pick(row, "variety", "品种", "商品名称") or parse_variety(contract))
    return {
        "exchange": exchange,
        "symbol": symbol.upper(),
        "contract": contract.upper(),
        "open": as_float(pick(row, "open", "开盘价", "今开盘")),
        "high": as_float(pick(row, "high", "最高价")),
        "low": as_float(pick(row, "low", "最低价")),
        "close": as_float(pick(row, "close", "收盘价", "今收盘")),
        # Most futures exchanges expose previous settlement, not previous close.
        "pre_close": as_float(pick(row, "pre_close", "pre_settle", "昨收盘", "前结算价")),
        "volume": as_float(pick(row, "volume", "成交量")),
        "open_interest": as_float(pick(row, "open_interest", "持仓量")),
        "turnover": as_float(pick(row, "turnover", "成交额")),
        "settlement": as_float(pick(row, "settle", "settlement", "结算价", "今结算")),
        "source": row.get("_source") or row.get("source") or "akshare",
        "source_note": row.get("_source_note") or "",
        "raw": row,
    }


def normalize_seat_row(exchange: str, row: dict[str, Any]) -> dict[str, Any]:
    contract = str(pick(row, "symbol", "合约", "合约代码", "contract", "_akshare_key") or "")
    variety = str(pick(row, "var", "variety", "品种", "商品") or parse_variety(contract))
    return {
        "exchange": exchange,
        "variety": variety.upper(),
        "contract": contract.upper(),
        "rank": int(as_float(pick(row, "rank", "名次", "排名")) or 0) or None,
        "vol_party_name": str(pick(row, "vol_party_name", "成交量会员简称", "成交量排名") or ""),
        "vol": as_float(pick(row, "vol", "成交量")),
        "vol_chg": as_float(pick(row, "vol_chg", "成交量变化")),
        "long_party_name": str(pick(row, "long_party_name", "持买单量会员简称", "多单会员") or ""),
        "long_open_interest": as_float(pick(row, "long_open_interest", "持买单量", "多单持仓")),
        "long_open_interest_chg": as_float(pick(row, "long_open_interest_chg", "持买单量变化")),
        "short_party_name": str(pick(row, "short_party_name", "持卖单量会员简称", "空单会员") or ""),
        "short_open_interest": as_float(pick(row, "short_open_interest", "持卖单量", "空单持仓")),
        "short_open_interest_chg": as_float(pick(row, "short_open_interest_chg", "持卖单量变化")),
        "raw": row,
    }
