from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any, Callable

import pandas as pd

from app.sources.dce_fallback_source import (
    fetch_dce_daily_from_sina,
    fetch_dce_seat_rank_from_sina,
)


EXCHANGES = ["DCE", "CZCE", "SHFE", "CFFEX", "GFEX", "INE"]
INE_VARIETIES = {"SC", "NR", "LU", "BC", "EC"}
DCE_NO_PROXY_HOSTS = "dce.com.cn,www.dce.com.cn,.dce.com.cn,*.dce.com.cn"


@contextmanager
def dce_direct_network():
    """Force DCE official-site calls to bypass proxy env vars.

    DCE frequently returns WAF/precondition errors and is sensitive to proxy
    egress. Keep this scoped to DCE calls so other data sources keep their
    normal network behaviour.
    """
    keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"]
    old = {key: os.environ.get(key) for key in keys}
    try:
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
            os.environ.pop(key, None)
        existing = [x.strip() for x in (old.get("NO_PROXY") or old.get("no_proxy") or "").split(",") if x.strip()]
        direct_hosts = [x for x in DCE_NO_PROXY_HOSTS.split(",") if x not in existing]
        no_proxy = ",".join(existing + direct_hosts)
        os.environ["NO_PROXY"] = no_proxy
        os.environ["no_proxy"] = no_proxy
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass(frozen=True)
class FetchResult:
    exchange: str
    kind: str
    rows: list[dict[str, Any]]
    error: str | None = None


def _variety_from_symbol(symbol: Any) -> str:
    import re
    m = re.match(r"([A-Za-z]+)", str(symbol or ""))
    return m.group(1).upper() if m else ""


def _records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None:
        return []
    cleaned = df.copy()
    # AkShare returns SHFE/INE numeric columns as object strings; normalize early.
    for col in ["open", "high", "low", "close", "volume", "open_interest", "turnover", "settle", "pre_settle"]:
        if col in cleaned.columns:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
    return cleaned.where(pd.notnull(cleaned), None).to_dict(orient="records")


def _call_with_retry(fn: Callable[[], Any], retries: int = 2) -> Any:
    last_exc: Exception | None = None
    for _ in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    assert last_exc is not None
    raise last_exc


class AkShareSource:
    """Thin adapter around AkShare.

    Keep all exchange-specific quirks here. Service layers should consume
    normalized dictionaries and never call AkShare directly.

    DCE daily and seat rank data are fetched via Sina fallback when the official
    DCE website (get_dce_daily) returns HTTP 412 or empty results.
    """

    def __init__(self) -> None:
        import akshare as ak
        self.ak = ak

    def fetch_daily(self, trade_date: str, exchange: str) -> FetchResult:
        exchange = exchange.upper()
        try:
            if exchange == "DCE":
                with dce_direct_network():
                    df = _call_with_retry(lambda: self.ak.get_dce_daily(date=trade_date))
                    if df is not None and not df.empty:
                        return FetchResult(exchange=exchange, kind="daily", rows=_records(df))
                # DCE official API returned empty; try Sina fallback
                fallback = fetch_dce_daily_from_sina(trade_date)
                return FetchResult(
                    exchange=exchange,
                    kind="daily",
                    rows=fallback.rows,
                    error=fallback.error or "DCE official returned empty; used Sina fallback",
                )
            elif exchange == "CZCE":
                df = _call_with_retry(lambda: self.ak.get_czce_daily(date=trade_date))
            elif exchange == "SHFE":
                df = _call_with_retry(lambda: self.ak.get_shfe_daily(date=trade_date))
            elif exchange == "CFFEX":
                df = _call_with_retry(lambda: self.ak.get_cffex_daily(date=trade_date))
            elif exchange == "GFEX":
                df = _call_with_retry(lambda: self.ak.get_gfex_daily(date=trade_date))
            elif exchange == "INE":
                df = _call_with_retry(lambda: self.ak.get_ine_daily(date=trade_date))
            else:
                raise ValueError(f"unsupported exchange: {exchange}")
            rows = _records(df)
            # AkShare's SHFE endpoint may include INE contracts; avoid double counting when INE is collected separately.
            if exchange == "SHFE":
                rows = [r for r in rows if str(r.get("variety") or _variety_from_symbol(r.get("symbol"))).upper() not in INE_VARIETIES]
            return FetchResult(exchange=exchange, kind="daily", rows=rows)
        except Exception as exc:  # noqa: BLE001
            # For DCE, try Sina fallback on any error (e.g. JSONDecodeError, HTTP 412)
            if exchange == "DCE":
                with dce_direct_network():
                    fallback = fetch_dce_daily_from_sina(trade_date)
                fallback_note = "used Sina fallback" if fallback.rows else "Sina fallback unavailable"
                error = fallback.error or f"{type(exc).__name__}: {exc}; {fallback_note}"
                return FetchResult(exchange=exchange, kind="daily", rows=fallback.rows, error=error)
            return FetchResult(exchange=exchange, kind="daily", rows=[], error=f"{type(exc).__name__}: {exc}")

    def fetch_seat_rank(self, trade_date: str, exchange: str) -> FetchResult:
        exchange = exchange.upper()
        try:
            if exchange == "DCE":
                with dce_direct_network():
                    data = self.ak.get_dce_rank_table(date=trade_date)
                    # get_dce_rank_table returns {} for recent dates (DCE site issue)
                    if isinstance(data, dict) and not data:
                        fallback = fetch_dce_seat_rank_from_sina(trade_date)
                        return FetchResult(
                            exchange=exchange,
                            kind="seat_rank",
                            rows=fallback.rows,
                            error=fallback.error,
                        )
            elif exchange == "CZCE":
                data = self.ak.get_rank_table_czce(date=trade_date)
            elif exchange == "SHFE":
                data = self.ak.get_shfe_rank_table(date=trade_date)
            elif exchange == "CFFEX":
                data = self.ak.get_cffex_rank_table(date=trade_date)
            elif exchange == "GFEX":
                data = self.ak.futures_gfex_position_rank(date=trade_date)
            elif exchange == "INE":
                return FetchResult(exchange=exchange, kind="seat_rank", rows=[], error="INE seat rank adapter not implemented yet")
            else:
                raise ValueError(f"unsupported exchange: {exchange}")

            if isinstance(data, dict):
                rows: list[dict[str, Any]] = []
                for key, df in data.items():
                    for row in _records(df):
                        row.setdefault("_akshare_key", key)
                        rows.append(row)
            else:
                rows = _records(data)
            if not rows:
                return FetchResult(exchange=exchange, kind="seat_rank", rows=[], error="source_unavailable: empty seat rank")
            return FetchResult(exchange=exchange, kind="seat_rank", rows=rows)
        except Exception as exc:  # noqa: BLE001
            return FetchResult(exchange=exchange, kind="seat_rank", rows=[], error=f"{type(exc).__name__}: {exc}")