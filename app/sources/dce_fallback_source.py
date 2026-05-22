"""
DCE Fallback Source Adapter — uses Sina futures API as fallback when AkShare DCE fails.

Fallback strategy for daily market:
  1. Fetch DCE main contract list via futures_display_main_sina()
  2. For each DCE variety (M, Y, C, L, PP, V, EG, PG, etc.), call futures_zh_daily_sina(symbol={variety}0)
  3. Map Sina columns (date, open, high, low, close, volume, hold, settle) to standard schema

Known limitations:
  - Sina "hold" (open_interest) reflects only the nearest contract, not exchange-wide open interest
  - Sina data has no turnover field (成交额); leave as None
  - Sina data has no pre_settle field; leave as None
  - Seat rank (持仓排名) from DCE has no stable fallback — both official API and AkShare
    adapters fail (BadZipFile / empty responses). The seat_rank will return error with
    clear diagnostic so the collector can record the failure but not crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


EXCHANGE = "DCE"


def _records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Replicated from akshare_source to avoid circular import."""
    if df is None:
        return []
    cleaned = df.copy()
    for col in ["open", "high", "low", "close", "volume", "open_interest", "turnover", "settle", "pre_settle"]:
        if col in cleaned.columns:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
    return cleaned.where(pd.notnull(cleaned), None).to_dict(orient="records")
DCE_EXCHANGE_CODE = "dce"  # for futures_display_main_sina filtering

# All DCE varieties that have continuous contracts in Sina
DCE_VARIETY_SYMBOLS = [
    "M",   # 豆粕
    "Y",   # 豆油
    "C",   # 玉米
    "L",   # 塑料 (聚乙烯)
    "PP",  # 聚丙烯
    "V",   # PVC
    "EG",  # 乙二醇
    "PG",  # 液化石油气
    "FB",  # 纤维板
    "BB",  # 胶合板
    "A",   # 豆一
    "B",   # 豆二
    "RM",  # 菜粕
    "CS",  # 玉米淀粉
    "JD",  # 鸡蛋
    "RR",  # 粳米
    "EB",  # 苯乙烯
    "LH",  # 生猪
    "J",   # 焦炭
    "JM",  # 焦煤
    "I",   # 铁矿石
    "P",   # 棕榈油
    "LG",  # 原木
    "BZ",  # 纯苯
]


@dataclass
class DceFallbackResult:
    """Normalized result from DCE fallback source."""
    rows: list[dict[str, Any]]
    error: str | None = None
    source: str = "dce_sina_fallback"


def fetch_dce_daily_from_sina(trade_date: str) -> DceFallbackResult:
    """
    Fetch DCE daily market data from Sina futures API as fallback.

    Sina's futures_zh_daily_sina works reliably for all DCE symbols, even when
    the official DCE website (get_dce_daily) returns HTTP 412.

    Args:
        trade_date: Trade date in YYYYMMDD format (e.g. "20260521")

    Returns:
        DceFallbackResult containing normalized rows and any error message
    """
    import akshare as ak

    all_rows = []
    errors = []

    # 1. Get the list of active DCE main contracts from Sina
    try:
        main_df = ak.futures_display_main_sina()
        dce_main = main_df[main_df["exchange"] == DCE_EXCHANGE_CODE]["symbol"].tolist()
    except Exception as e:
        errors.append(f"futures_display_main_sina: {type(e).__name__}: {e}")
        # Fall back to known DCE symbols
        dce_main = [f"{s}0" for s in DCE_VARIETY_SYMBOLS]

    # 2. Fetch daily data for each DCE symbol
    for symbol in dce_main:
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
            if df is None or df.empty:
                continue

            # Filter to the requested trade_date
            # Sina returns date in format "2026-05-21"
            target_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            if "date" not in df.columns:
                continue

            df_filtered = df[df["date"] == target_date]
            if df_filtered.empty:
                continue

            row = df_filtered.iloc[0].to_dict()

            # Parse variety from symbol (e.g. "M0" → "M")
            variety = symbol.rstrip("0123456789").upper()
            if not variety:
                variety = symbol[:1]  # fallback: first character

            # Map Sina fields to standard schema
            normalized = {
                "symbol": variety.upper(),       # variety code (e.g. "M")
                "contract": _sina_symbol_to_contract(symbol, trade_date),
                "date": trade_date,
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume")),
                "open_interest": _safe_float(row.get("hold")),  # Sina calls it "hold"
                "turnover": None,                 # Sina has no turnover
                "settle": _safe_float(row.get("settle")),
                "pre_settle": None,               # Sina has no pre_settle
                "variety": variety.upper(),
                # Extra fields from Sina source
                "_sina_date": row.get("date"),
                "_source": "futures_zh_daily_sina",
                "_raw_symbol": symbol,
            }
            all_rows.append(normalized)

        except Exception as e:
            errors.append(f"{symbol}: {type(e).__name__}: {e}")
            continue

    if not all_rows and errors:
        return DceFallbackResult(rows=[], error=f"DCE Sina fallback failed: {'; '.join(errors[:5])}")

    return DceFallbackResult(rows=all_rows, error=None)


def fetch_dce_seat_rank_from_sina(trade_date: str) -> DceFallbackResult:
    """
    DCE seat rank has NO working fallback.
    
    Both official DCE API and AkShare adapters fail:
    - get_dce_rank_table(): returns {} (empty) for recent dates
    - futures_dce_position_rank(): BadZipFile (ZIP from DCE is corrupted/missing)
    
    Sina does not provide member/ seat rank data.
    
    This function always returns an error result rather than partial/bogus data.
    """
    return DceFallbackResult(
        rows=[],
        error=(
            "DCE seat rank fallback unavailable. "
            "Both get_dce_rank_table (returns empty {}) and futures_dce_position_rank "
            "(BadZipFile) fail. No public fallback source exists for DCE member trading positions. "
            "Recommendations: (1) Monitor DCE official site for API restoration, "
            "(2) Consider Tushare Pro or other commercial data feeds for DCE seat rank."
        ),
        source="dce_seat_rank_none",
    )


def _sina_symbol_to_contract(sina_symbol: str, trade_date: str) -> str:
    """Return Sina continuous-contract code as-is.

    Sina symbols like ``M0``/``V0`` are continuous/main-contract series, not an
    exchange-listed contract. Fabricating a month code from the trade date is
    misleading, so keep the explicit continuous code and mark source metadata.
    """
    return sina_symbol.upper()


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None