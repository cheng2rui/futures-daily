from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CapitalFlowDaily, Contract, DailyBar, JobRun, WatchSymbol
from app.metadata.variety_meta import get_variety_name
from app.services.collector import collect_daily_market
from app.services.news_collector import collect_news_digest, load_latest_news_digest
from app.services.structure import sector_for
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/markets", tags=["markets"])


def _now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _latest_trade_date(db: Session) -> str | None:
    return db.scalar(select(DailyBar.trade_date).group_by(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))


def _empty_intraday(collect_result: dict | None = None) -> dict:
    return {
        "mode": "intraday",
        "trade_date": "",
        "updated_at": _now_text(),
        "watermark_id": 0,
        "disclaimer": "非实时行情，仅基于最近一次阶段性采集结果。",
        "collect": collect_result,
        "market": {"contracts": 0, "main_contracts": 0, "up_count": 0, "down_count": 0, "flat_count": 0, "volume": 0, "volume_prev": 0, "volume_delta": 0, "volume_delta_pct": 0, "open_interest": 0, "turnover": 0, "capital_flow_amount": 0, "capital_inflow_amount": 0, "capital_outflow_amount": 0},
        "rankings": {"gainers": [], "losers": [], "volume": []},
        "watch_symbols": [],
        "sectors": [],
        "intelligence": {"news_digest": {"items": [], "viewpoints": [], "summary": {}, "status": "missing"}},
    }


def _change_pct(bar: DailyBar) -> float | None:
    close = bar.close
    base = bar.pre_close or bar.settlement or bar.open
    if close is None or not base:
        return None
    try:
        return round((float(close) - float(base)) / float(base) * 100, 2)
    except ZeroDivisionError:
        return None


def _bar_payload(bar: DailyBar, meta: dict[tuple[str, str], Contract]) -> dict:
    contract = meta.get(((bar.exchange or "").upper(), (bar.symbol or "").upper()))
    return {
        "trade_date": bar.trade_date,
        "exchange": bar.exchange,
        "symbol": bar.symbol,
        "name": contract.name if contract and contract.name else get_variety_name(bar.symbol),
        "sector": contract.sector if contract and contract.sector else sector_for(bar.symbol),
        "contract": bar.contract,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "pre_close": bar.pre_close,
        "change_pct": _change_pct(bar),
        "volume": bar.volume,
        "open_interest": bar.open_interest,
        "turnover": bar.turnover,
    }


def _watch_variety(symbol: str) -> str:
    text = (symbol or "").upper()
    return "".join(ch for ch in text if ch.isalpha())


def _main_contracts(rows: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.get("exchange") or "", row.get("symbol") or "")
        old = by_key.get(key)
        if old is None or float(row.get("volume") or 0) > float(old.get("volume") or 0):
            by_key[key] = {**row, "main_contract": row.get("contract")}
    return list(by_key.values())


def _sector_summary(rows: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        name = row.get("sector") or "未分类"
        bucket = buckets.setdefault(name, {"name": name, "count": 0, "up": 0, "down": 0, "volume": 0.0, "open_interest": 0.0, "changes": []})
        change = row.get("change_pct")
        bucket["count"] += 1
        bucket["volume"] += float(row.get("volume") or 0)
        bucket["open_interest"] += float(row.get("open_interest") or 0)
        if change is not None:
            bucket["changes"].append(float(change))
            if change > 0:
                bucket["up"] += 1
            elif change < 0:
                bucket["down"] += 1
    result = []
    for bucket in buckets.values():
        changes = bucket.pop("changes")
        bucket["avg_change"] = round(sum(changes) / len(changes), 2) if changes else 0
        bucket["up_ratio"] = round(bucket["up"] / bucket["count"] * 100, 1) if bucket["count"] else 0
        result.append(bucket)
    return sorted(result, key=lambda x: abs(float(x.get("avg_change") or 0)), reverse=True)


@router.post("/intraday/refresh")
def refresh_intraday_snapshot(trade_date: str | None = None, db: Session = Depends(get_db)):
    selected_date = normalize_trade_date(trade_date)
    job = JobRun(name="refresh_intraday", status="running", trade_date=selected_date, started_at=datetime.utcnow(), message="manual intraday refresh")
    db.add(job)
    db.commit()
    try:
        collect_result = collect_daily_market(db, selected_date)
        try:
            news_result = collect_news_digest(db, selected_date)
        except Exception as news_exc:  # noqa: BLE001
            news_result = {"error": f"{type(news_exc).__name__}: {news_exc}", "saved": 0, "rows": 0}
        payload = _build_intraday_snapshot(db, selected_date, collect_result)
        total_saved = sum(int(x.get("saved") or 0) for x in collect_result.get("results", [])) if collect_result else 0
        failed = [x for x in collect_result.get("results", []) if x.get("error")] if collect_result else []
        job.status = "partial" if failed and total_saved else "failed" if failed else "success"
        news_saved = int((news_result or {}).get("saved") or 0)
        job.message = f"盘中快照刷新完成，保存 {total_saved} 行，资讯 {news_saved} 条" + (f"，异常 {len(failed)} 个" if failed else "")
        job.result_json = json.dumps({"collect": collect_result, "news": news_result, "snapshot": {"market": payload.get("market"), "updated_at": payload.get("updated_at")}}, ensure_ascii=False, default=str)
        job.finished_at = datetime.utcnow()
        db.commit()
        payload["job_id"] = job.id
        payload["job_status"] = job.status
        return payload
    except Exception as exc:
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"
        job.finished_at = datetime.utcnow()
        db.commit()
        raise


@router.get("/intraday")
def intraday_snapshot(trade_date: str | None = None, refresh: bool = False, db: Session = Depends(get_db)):
    """Stage-based intraday snapshot built from the latest collected daily bars.

    This is intentionally not a real-time trading feed. When refresh=true, it
    triggers the existing market collector and then summarizes the latest saved
    rows for dashboard use.
    """
    if refresh:
        return refresh_intraday_snapshot(trade_date, db)
    selected_date = normalize_trade_date(trade_date) if trade_date else _latest_trade_date(db)
    return _build_intraday_snapshot(db, selected_date)


def _build_intraday_snapshot(db: Session, selected_date: str | None, collect_result: dict | None = None) -> dict:
    if not selected_date:
        return _empty_intraday(collect_result)

    bars = db.scalars(select(DailyBar).where(DailyBar.trade_date == selected_date)).all()
    contracts = db.scalars(select(Contract)).all()
    meta = {((c.exchange or "").upper(), (c.symbol or "").upper()): c for c in contracts}
    watch_symbols = db.scalars(select(WatchSymbol).where(WatchSymbol.enabled == True).order_by(WatchSymbol.sort_order, WatchSymbol.symbol)).all()  # noqa: E712
    watch_keys = {((w.exchange or "").upper(), _watch_variety(w.symbol)) for w in watch_symbols if _watch_variety(w.symbol)}
    watch_symbol_only = {_watch_variety(w.symbol) for w in watch_symbols if not w.exchange and _watch_variety(w.symbol)}
    watch_contracts = {(w.symbol or "").upper() for w in watch_symbols if any(ch.isdigit() for ch in (w.symbol or ""))}

    rows = [_bar_payload(bar, meta) for bar in bars]
    news_digest = load_latest_news_digest(db, selected_date)
    liquid_rows = [r for r in rows if (r.get("volume") or 0) > 0 and (r.get("close") or 0) > 0]
    main_rows = _main_contracts(liquid_rows)
    up = sum(1 for r in main_rows if (r.get("change_pct") or 0) > 0)
    down = sum(1 for r in main_rows if (r.get("change_pct") or 0) < 0)
    flat = max(0, len(main_rows) - up - down)
    updated_at = max((b.id for b in bars), default=0)
    total_volume = sum(float(r.get("volume") or 0) for r in rows)
    total_turnover = sum(float(r.get("turnover") or 0) for r in rows)
    capital_flow_rows = list(db.scalars(select(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == selected_date)))
    capital_flow_amount = sum(float(row.amount or 0) for row in capital_flow_rows)
    capital_inflow_amount = sum(float(row.amount or 0) for row in capital_flow_rows if (row.amount or 0) > 0)
    capital_outflow_amount = sum(float(row.amount or 0) for row in capital_flow_rows if (row.amount or 0) < 0)
    prev_volume = previous_total_volume(db, selected_date)
    volume_delta = total_volume - prev_volume if prev_volume is not None else None
    volume_delta_pct = round(volume_delta / prev_volume * 100, 1) if volume_delta is not None and prev_volume else None

    return {
        "mode": "intraday",
        "trade_date": selected_date,
        "updated_at": _now_text(),
        "watermark_id": updated_at,
        "disclaimer": "非实时行情，仅基于最近一次阶段性采集结果。",
        "collect": collect_result,
        "market": {
            "contracts": len(rows),
            "main_contracts": len(main_rows),
            "up_count": up,
            "down_count": down,
            "flat_count": flat,
            "volume": total_volume,
            "volume_prev": prev_volume,
            "volume_delta": volume_delta,
            "volume_delta_pct": volume_delta_pct,
            "turnover": total_turnover,
            "capital_flow_amount": capital_flow_amount,
            "capital_inflow_amount": capital_inflow_amount,
            "capital_outflow_amount": capital_outflow_amount,
            "open_interest": sum(float(r.get("open_interest") or 0) for r in rows),
        },
        "rankings": {
            "gainers": sorted(main_rows, key=lambda r: r.get("change_pct") if r.get("change_pct") is not None else -999, reverse=True)[:10],
            "losers": sorted(main_rows, key=lambda r: r.get("change_pct") if r.get("change_pct") is not None else 999)[:10],
            "volume": sorted(liquid_rows, key=lambda r: float(r.get("volume") or 0), reverse=True)[:10],
        },
        "watch_symbols": [r for r in main_rows if ((r.get("exchange"), r.get("symbol")) in watch_keys or r.get("symbol") in watch_symbol_only or (r.get("contract") or "").upper() in watch_contracts)],
        "sectors": _sector_summary(main_rows),
        "intelligence": {"news_digest": news_digest},
    }


def previous_total_volume(db: Session, trade_date: str) -> float | None:
    prev_date = db.scalar(select(DailyBar.trade_date).where(DailyBar.trade_date < trade_date).group_by(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))
    if not prev_date:
        return None
    bars = db.scalars(select(DailyBar.volume).where(DailyBar.trade_date == prev_date)).all()
    return sum(float(v or 0) for v in bars)


@router.get("/bars")
def list_bars(trade_date: str | None = None, symbol: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    stmt = select(DailyBar).order_by(desc(DailyBar.trade_date), DailyBar.exchange, DailyBar.contract).limit(limit)
    if trade_date:
        stmt = stmt.where(DailyBar.trade_date == trade_date)
    if symbol:
        stmt = stmt.where(DailyBar.symbol == symbol.upper())
    rows = db.scalars(stmt).all()
    return [
        {
            "trade_date": r.trade_date,
            "exchange": r.exchange,
            "symbol": r.symbol,
            "contract": r.contract,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "open_interest": r.open_interest,
            "turnover": r.turnover,
        }
        for r in rows
    ]


@router.get("/watch-symbols")
def list_watch_symbols(db: Session = Depends(get_db)):
    rows = db.scalars(select(WatchSymbol).order_by(WatchSymbol.sort_order, WatchSymbol.symbol)).all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "exchange": r.exchange,
            "name": r.name,
            "sector": r.sector,
            "enabled": r.enabled,
            "sort_order": r.sort_order,
            "note": r.note,
        }
        for r in rows
    ]
