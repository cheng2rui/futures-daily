from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.metadata.contract_specs import get_point_value
from app.metadata.variety_meta import get_exchange_code, get_variety_name
from app.models import DailyBar, Report, SeatRankRow, WatchSymbol, SeatWatchlist
from app.services.data_mart import build_variety_dataset, materialize_variety_dataset
from app.services.data_quality import build_data_quality
from app.services.seat_archive import load_archive_summary
from app.services.structure import build_structure, pct_change, sector_for


def notional_value(bar: DailyBar) -> float | None:
    pv = get_point_value(bar.symbol)
    if pv is None or bar.close is None or bar.open_interest is None:
        return None
    return round(bar.close * bar.open_interest * pv, 2)


def build_report(db: Session, trade_date: str) -> Report:
    bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date == trade_date)))
    changes = [(bar, pct_change(bar)) for bar in bars]
    valid = [(bar, chg) for bar, chg in changes if chg is not None]

    up_count = sum(1 for _, chg in valid if chg > 0)
    down_count = sum(1 for _, chg in valid if chg < 0)
    turnover = sum((bar.turnover or 0) for bar in bars)
    volume = sum((bar.volume or 0) for bar in bars)

    sector_bucket: dict[str, list[float]] = defaultdict(list)
    for bar, chg in valid:
        sector_bucket[sector_for(bar.symbol)].append(chg)
    sectors = [
        {"name": name, "avg_change": round(sum(vals) / len(vals), 2), "count": len(vals)}
        for name, vals in sector_bucket.items() if vals
    ]
    sectors.sort(key=lambda x: x["avg_change"], reverse=True)

    gainers = sorted(valid, key=lambda x: x[1], reverse=True)[:10]
    losers = sorted(valid, key=lambda x: x[1])[:10]
    volume_top = sorted(bars, key=lambda x: x.volume or 0, reverse=True)[:10]
    oi_top = sorted(bars, key=lambda x: x.open_interest or 0, reverse=True)[:10]

    seat_rows = list(db.scalars(select(SeatRankRow).where(SeatRankRow.trade_date == trade_date).limit(5000)))
    seat_long = sorted(
        [r for r in seat_rows if r.long_party_name and r.long_open_interest_chg is not None and (r.rank or 999) <= 20],
        key=lambda r: r.long_open_interest_chg or 0,
        reverse=True,
    )[:10]
    seat_short = sorted(
        [r for r in seat_rows if r.short_party_name and r.short_open_interest_chg is not None and (r.rank or 999) <= 20],
        key=lambda r: r.short_open_interest_chg or 0,
        reverse=True,
    )[:10]

    valid_count = max(1, up_count + down_count)
    heat = round(up_count / valid_count * 100, 1)
    risk = round(down_count / valid_count * 100, 1)
    score = round((heat + (100 - risk)) / 2, 1)
    stage = "偏强" if score >= 65 else "偏弱" if score <= 40 else "分化"

    def bar_item(bar: DailyBar, chg: float | None = None) -> dict:
        raw = {}
        try:
            raw = json.loads(bar.raw_json or "{}")
        except Exception:
            raw = {}
        return {
            "exchange": get_exchange_code(bar.symbol, bar.exchange),
            "symbol": bar.symbol,
            "name": get_variety_name(bar.symbol),
            "contract": bar.contract,
            "sector": sector_for(bar.symbol),
            "close": bar.close,
            "change_pct": round(chg, 2) if chg is not None else None,
            "volume": bar.volume,
            "open_interest": bar.open_interest,
            "turnover": bar.turnover,
            "notional_oi": notional_value(bar),
            "source": raw.get("_source") or raw.get("source") or "akshare",
        }

    data_quality = build_data_quality(db, trade_date)
    structure = build_structure(bars)
    seat_archive = load_archive_summary(trade_date)
    dataset = build_variety_dataset(db, trade_date)
    materialize_variety_dataset(db, trade_date)
    watch_symbols = list(db.scalars(select(WatchSymbol).where(WatchSymbol.enabled == True)))  # noqa: E712
    watch_symbol_codes = {w.symbol.upper() for w in watch_symbols}
    watch_bars = [bar_item(b, pct_change(b)) for b in bars if b.symbol.upper() in watch_symbol_codes]
    watch_seats = list(db.scalars(select(SeatWatchlist).where(SeatWatchlist.enabled == True)))  # noqa: E712
    watch_seat_names = {s.seat_name for s in watch_seats}
    watch_seat_rows = [
        seat_watch_item(r)
        for r in seat_rows
        if r.long_party_name in watch_seat_names or r.short_party_name in watch_seat_names or r.vol_party_name in watch_seat_names
    ][:50]

    payload = {
        "date": trade_date,
        "meta": {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "version": "0.1.0"},
        "overview": {
            "score": score,
            "stage": stage,
            "heat": heat,
            "risk": risk,
            "summary": f"上涨 {up_count} 个、下跌 {down_count} 个；市场状态：{stage}。",
        },
        "market": {"up_count": up_count, "down_count": down_count, "turnover": turnover, "volume": volume, "contracts": len(bars)},
        "sectors": sectors,
        "rankings": {
            "gainers": [bar_item(b, c) for b, c in gainers],
            "losers": [bar_item(b, c) for b, c in losers],
            "volume": [bar_item(b) for b in volume_top],
            "open_interest": [bar_item(b) for b in oi_top],
        },
        "structure": structure,
        "seats": {
            "long_increase_top": [seat_item(r, "long") for r in seat_long],
            "short_increase_top": [seat_item(r, "short") for r in seat_short],
            "watchlist": watch_seat_rows,
            "archive": seat_archive,
        },
        "watch_symbols": watch_bars,
        "data_quality": data_quality,
        "dataset": {
            "count": dataset.get("count", 0),
            "summary": dataset.get("summary", {}),
            "top_net_delta": sorted(
                [r for r in dataset.get("rows", []) if r.get("archive_signal") and r["archive_signal"].get("netDelta") is not None],
                key=lambda x: abs(x["archive_signal"].get("netDelta") or 0),
                reverse=True,
            )[:10],
        },
        "risk_flags": quality_flags(data_quality),
        "action_notes": ["MVP 自动摘要，仅作市场复盘参考。"],
    }

    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        report = Report(trade_date=trade_date)
    report.status = "generated"
    report.score = score
    report.summary = payload["overview"]["summary"]
    report.report_json = json.dumps(payload, ensure_ascii=False, default=str)
    report.generated_at = datetime.utcnow()
    report.updated_at = datetime.utcnow()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def quality_flags(data_quality: dict) -> list[str]:
    if data_quality.get("status") == "ok":
        return []
    flags = [f"数据覆盖 {data_quality.get('coverage_pct', 0)}%，部分交易所采集失败。"]
    failed = [x["exchange"] for x in data_quality.get("exchanges", []) if x.get("status") == "failed"]
    if failed:
        flags.append("失败交易所：" + "、".join(failed))
    return flags


def seat_watch_item(row: SeatRankRow) -> dict:
    return {
        "exchange": row.exchange,
        "variety": row.variety,
        "contract": row.contract,
        "rank": row.rank,
        "vol_party_name": row.vol_party_name,
        "vol": row.vol,
        "vol_chg": row.vol_chg,
        "long_party_name": row.long_party_name,
        "long_open_interest": row.long_open_interest,
        "long_open_interest_chg": row.long_open_interest_chg,
        "short_party_name": row.short_party_name,
        "short_open_interest": row.short_open_interest,
        "short_open_interest_chg": row.short_open_interest_chg,
    }


def seat_item(row: SeatRankRow, side: str) -> dict:
    return {
        "exchange": row.exchange,
        "variety": row.variety,
        "contract": row.contract,
        "rank": row.rank,
        "seat": row.long_party_name if side == "long" else row.short_party_name,
        "value": row.long_open_interest if side == "long" else row.short_open_interest,
        "change": row.long_open_interest_chg if side == "long" else row.short_open_interest_chg,
    }
