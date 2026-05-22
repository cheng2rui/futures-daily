from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import time

import requests


DATACENTER_BASE = "https://api.quheqihuo.com/api/v2/datacenter"
WWW_BASE = "https://www.quheqihuo.com"


@dataclass(frozen=True)
class QuheResult:
    kind: str
    rows: list[dict[str, Any]]
    error: str | None = None
    meta: dict[str, Any] | None = None


class QuheSource:
    """Third-party data source from quheqihuo.com.

    This is an enhancement/fallback source, not an official exchange source.
    Keep source labels explicit when persisting rows.
    """

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://m.quheqihuo.com/data/zijin.html",
            "Accept": "application/json,text/javascript,*/*;q=0.01",
        })

    def _get_json(self, url: str, params: dict[str, Any] | None = None, retries: int = 2, delay: float = 0.25) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                text = r.text.strip()
                if not text:
                    raise ValueError(f"empty response status={r.status_code}")
                return r.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    time.sleep(delay * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    def _result(self, kind: str, url: str, params: dict[str, Any] | None = None, data_path: str = "data") -> QuheResult:
        try:
            payload = self._get_json(url, params=params)
            ok = payload.get("returnCode", payload.get("code")) == 0 or payload.get("code") == 0
            if not ok:
                return QuheResult(kind=kind, rows=[], error=payload.get("message") or payload.get("msg") or "non-zero return code", meta=payload)
            data = payload.get(data_path)
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                return QuheResult(kind=kind, rows=data.get("data") or [], meta={"time": data.get("time"), "raw": payload})
            if isinstance(data, list):
                return QuheResult(kind=kind, rows=data, meta={"raw": payload})
            return QuheResult(kind=kind, rows=[], error="unexpected data format", meta=payload)
        except Exception as exc:  # noqa: BLE001
            return QuheResult(kind=kind, rows=[], error=f"{type(exc).__name__}: {exc}")

    def fetch_capital_flow(self) -> QuheResult:
        return self._result("capital_flow", f"{WWW_BASE}/api/exchange_variety/capital")

    def fetch_basis(self) -> QuheResult:
        return self._result("basis", f"{DATACENTER_BASE}/app/basis/getBasisDataList.html")

    def fetch_warehouse_receipts(self) -> QuheResult:
        return self._result("warehouse_receipt", f"{DATACENTER_BASE}/app/position/positionOrder.html")

    def fetch_contract_tree(self) -> QuheResult:
        return self._result("contract_tree", f"{WWW_BASE}/api/exchange_variety/tree_by_product_code")

    def fetch_available_trading_days(self) -> QuheResult:
        return self._result("available_trading_days", f"{DATACENTER_BASE}/futures/getAvailableTradingDay/")

    def fetch_position_rank(self, symbol_code: str, trade_date_dash: str, side_type: int) -> QuheResult:
        return self._result(
            "position_rank",
            f"{DATACENTER_BASE}/app/position/rank.html",
            params={"symbolCode": symbol_code, "transactionTime": trade_date_dash, "type": side_type},
        )

    def fetch_history_holding(self, symbol_code: str, limit: int = 1500) -> QuheResult:
        return self._result(
            "history_holding",
            f"{DATACENTER_BASE}/app/futures/getFuturesHistoryHolding.html",
            params={"symbolCode": symbol_code, "sum": limit},
        )


def ms_to_datetime(value: Any) -> datetime | None:
    try:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value) / 1000)
    except Exception:
        return None


def dash_to_date8(value: str | None) -> str:
    return (value or "").replace("-", "")[:8]


def date8_to_dash(value: str) -> str:
    text = str(value or "")
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text
