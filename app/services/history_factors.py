from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BasisDaily, DailyBar, VarietyDailyFact, WarehouseReceiptDaily
from app.services.structure import pct_change

DEFAULT_WINDOWS = (20, 60, 120)
MIN_HISTORY_POINTS = 5


@dataclass(frozen=True)
class HistoryMetric:
    key: str
    label: str
    current: float | None
    window: int
    count: int
    percentile: float | None
    z_score: float | None
    status: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "current": self.current,
            "window": self.window,
            "count": self.count,
            "percentile": self.percentile,
            "z_score": self.z_score,
            "status": self.status,
            "note": self.note,
        }


def build_history_context(db: Session, trade_date: str, windows: tuple[int, ...] = DEFAULT_WINDOWS) -> dict[str, dict[str, Any]]:
    """Build per-symbol historical percentile context from existing daily bars.

    Uses only data already in the local database. If the local history is too
    short, the output explicitly marks `insufficient_history` instead of making
    a weak claim.
    """
    bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date <= trade_date).order_by(DailyBar.trade_date)))
    basis_rows = list(db.scalars(select(BasisDaily).where(BasisDaily.trade_date <= trade_date).order_by(BasisDaily.trade_date)))
    warehouse_rows = list(db.scalars(select(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date <= trade_date).order_by(WarehouseReceiptDaily.trade_date)))
    fact_rows = list(db.scalars(select(VarietyDailyFact).where(VarietyDailyFact.trade_date <= trade_date).order_by(VarietyDailyFact.trade_date)))

    basis_series = group_external_series(basis_rows, "basis_rate")
    warehouse_series = group_external_series(warehouse_rows, "increase_number")
    seat_series = group_fact_series(fact_rows, "archive_net_delta", fallback_field="seat_net_delta_top20")

    grouped: dict[tuple[str, str], dict[str, list[DailyBar]]] = {}
    for bar in bars:
        key = (str(bar.exchange or "").upper(), str(bar.symbol or "").upper())
        grouped.setdefault(key, {}).setdefault(bar.trade_date, []).append(bar)

    out: dict[str, dict[str, Any]] = {}
    for (_exchange, symbol), by_date in grouped.items():
        dates = sorted(by_date)
        if trade_date not in by_date:
            continue
        daily_series = [variety_daily_point(date, by_date[date]) for date in dates]
        idx = next((i for i, item in enumerate(daily_series) if item["trade_date"] == trade_date), -1)
        if idx < 0:
            continue
        metrics: list[dict[str, Any]] = []
        for window in windows:
            start = max(0, idx - window + 1)
            sample = daily_series[start : idx + 1]
            current = daily_series[idx]
            metrics.extend([
                metric("change_pct", "涨跌幅", current.get("change_pct"), [x.get("change_pct") for x in sample], window),
                metric("volume", "成交量", current.get("volume"), [x.get("volume") for x in sample], window),
                metric("open_interest", "持仓量", current.get("open_interest"), [x.get("open_interest") for x in sample], window),
            ])
            metrics.extend(external_metrics(symbol, trade_date, window, basis_series, warehouse_series, seat_series))
        valid = [m for m in metrics if m.get("status") == "ok" and m.get("percentile") is not None]
        highlights = sorted(valid, key=lambda x: abs(float(x.get("percentile") or 50) - 50), reverse=True)[:3]
        out[symbol] = {
            "symbol": symbol,
            "trade_date": trade_date,
            "metrics": metrics,
            "highlights": highlights,
            "status": "ok" if valid else "insufficient_history",
            "summary": summarize_highlights(highlights) if valid else "本地历史样本不足，暂不判断历史极端程度。",
        }
    return out


def variety_daily_point(trade_date: str, bars: list[DailyBar]) -> dict[str, Any]:
    main = pick_main_contract(bars)
    return {
        "trade_date": trade_date,
        "change_pct": pct_change(main),
        "volume": sum_num(x.volume for x in bars),
        "open_interest": sum_num(x.open_interest for x in bars),
    }


def pick_main_contract(items: list[DailyBar]) -> DailyBar:
    return sorted(items, key=lambda x: ((x.volume or 0) * 0.65 + (x.open_interest or 0) * 0.35), reverse=True)[0]


def group_external_series(rows: list[Any], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], Any] = {}
    for row in rows:
        symbol = str(getattr(row, "symbol", "") or "").upper()
        date = str(getattr(row, "trade_date", "") or "")
        if not symbol or not date:
            continue
        # Keep the first row per date/symbol. Upstream collectors already apply
        # source-priority when building daily reports; historical factor only
        # needs one stable value per day.
        grouped.setdefault((symbol, date), row)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for (symbol, date), row in grouped.items():
        by_symbol.setdefault(symbol, []).append({"trade_date": date, "value": safe_float(getattr(row, field, None))})
    for items in by_symbol.values():
        items.sort(key=lambda x: x["trade_date"])
    return by_symbol


def group_fact_series(rows: list[VarietyDailyFact], field: str, fallback_field: str | None = None) -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.symbol or "").upper()
        value = safe_float(getattr(row, field, None))
        if value is None and fallback_field:
            value = safe_float(getattr(row, fallback_field, None))
        by_symbol.setdefault(symbol, []).append({"trade_date": row.trade_date, "value": value})
    for items in by_symbol.values():
        items.sort(key=lambda x: x["trade_date"])
    return by_symbol


def external_metrics(
    symbol: str,
    trade_date: str,
    window: int,
    basis_series: dict[str, list[dict[str, Any]]],
    warehouse_series: dict[str, list[dict[str, Any]]],
    seat_series: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [
        series_metric("basis_rate", "基差率", symbol, trade_date, window, basis_series),
        series_metric("warehouse_delta", "仓单变化", symbol, trade_date, window, warehouse_series),
        series_metric("seat_net_delta", "席位净变化", symbol, trade_date, window, seat_series),
    ]


def series_metric(key: str, label: str, symbol: str, trade_date: str, window: int, series_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    series = series_by_symbol.get(symbol, [])
    idx = next((i for i, item in enumerate(series) if item.get("trade_date") == trade_date), -1)
    if idx < 0:
        return metric(key, label, None, [], window)
    sample = series[max(0, idx - window + 1) : idx + 1]
    current = sample[-1].get("value")
    return metric(key, label, current, [x.get("value") for x in sample], window)


def metric(key: str, label: str, current: Any, values: list[Any], window: int) -> dict[str, Any]:
    cur = safe_float(current)
    sample = [safe_float(x) for x in values]
    sample = [x for x in sample if x is not None]
    if cur is None or len(sample) < MIN_HISTORY_POINTS:
        return HistoryMetric(key, label, cur, window, len(sample), None, None, "insufficient_history", f"近 {window} 日有效样本 {len(sample)} 个，不足 {MIN_HISTORY_POINTS} 个。" ).as_dict()
    pct = percentile_rank(cur, sample)
    z = z_score(cur, sample)
    return HistoryMetric(
        key=key,
        label=label,
        current=round(cur, 4),
        window=window,
        count=len(sample),
        percentile=round(pct, 1),
        z_score=round(z, 2) if z is not None else None,
        status="ok",
        note=metric_note(label, window, pct),
    ).as_dict()


def percentile_rank(current: float, sample: list[float]) -> float:
    below = sum(1 for x in sample if x < current)
    equal = sum(1 for x in sample if x == current)
    return (below + 0.5 * equal) / len(sample) * 100


def z_score(current: float, sample: list[float]) -> float | None:
    if len(sample) < 2:
        return None
    sigma = pstdev(sample)
    if not sigma:
        return None
    return (current - mean(sample)) / sigma


def metric_note(label: str, window: int, percentile: float) -> str:
    if percentile >= 90:
        return f"{label}处于近 {window} 日高位区间。"
    if percentile <= 10:
        return f"{label}处于近 {window} 日低位区间。"
    return f"{label}处于近 {window} 日中性区间。"


def summarize_highlights(highlights: list[dict[str, Any]]) -> str:
    if not highlights:
        return "历史位置暂不突出。"
    parts = []
    for item in highlights[:3]:
        pct = item.get("percentile")
        direction = "高位" if pct is not None and pct >= 50 else "低位"
        parts.append(f"{item.get('label')}近{item.get('window')}日{direction}{pct}%")
    return "；".join(parts)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def sum_num(values) -> float:
    total = 0.0
    seen = False
    for value in values:
        n = safe_float(value)
        if n is not None:
            total += n
            seen = True
    return total if seen else 0.0
