from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.metadata.contract_specs import get_point_value
from app.metadata.variety_meta import VARIETY_META_BY_SYMBOL, get_exchange_code, get_variety_name
from app.models import BasisDaily, CapitalFlowDaily, DailyBar, DailyCoverage, QuheHistoryHolding, SeatRankRow, VarietyDailyFact, WarehouseReceiptDaily
from app.services.seat_archive import load_archive_summary
from app.services.structure import pct_change, sector_for


def build_variety_dataset(db: Session, trade_date: str) -> dict[str, Any]:
    """Build a usable per-variety data mart for analysis/UI/assistant.

    Raw storage is intentionally granular:
    - daily_bars: contract-level rows
    - seat_rank_rows: rank-row-level rows
    - rsstsx archive: variety-level seat signals

    This function turns those loose pieces into one normalized variety-level
    dataset. It is read-only for now; later we can materialize it into tables.
    """
    bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date == trade_date)))
    seats = list(db.scalars(select(SeatRankRow).where(SeatRankRow.trade_date == trade_date)))
    archive = load_archive_summary(trade_date)

    grouped_bars: dict[tuple[str, str], list[DailyBar]] = defaultdict(list)
    for bar in bars:
        grouped_bars[(get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper())].append(bar)

    archive_by_key = build_archive_index(archive)
    seat_by_key = summarize_seat_rows(seats)
    capital_by_symbol = {r.symbol.upper(): r for r in db.scalars(select(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date))}
    basis_by_symbol = pick_rows_by_source_priority(
        db.scalars(select(BasisDaily).where(BasisDaily.trade_date == trade_date)),
        ["quheqihuo", "akshare_100ppi"],
    )
    warehouse_by_symbol = pick_rows_by_source_priority(
        db.scalars(select(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date)),
        ["quheqihuo", "akshare_official"],
    )
    history_by_symbol = {r.symbol.upper(): r for r in db.scalars(select(QuheHistoryHolding).where(QuheHistoryHolding.trade_date == trade_date))}

    rows: list[dict[str, Any]] = []
    for (exchange, symbol), items in grouped_bars.items():
        main = pick_main_contract(items)
        name = get_variety_name(symbol)
        key_candidates = match_keys(symbol, name)
        archive_signal = first_match(archive_by_key, key_candidates)
        seat_summary = seat_by_key.get((exchange, symbol)) or first_match(seat_by_key, key_candidates) or {}
        change = pct_change(main)
        point_value = get_point_value(symbol)
        external_signals = external_signal_item(capital_by_symbol.get(symbol), basis_by_symbol.get(symbol), warehouse_by_symbol.get(symbol), history_by_symbol.get(symbol))
        rows.append({
            "trade_date": trade_date,
            "exchange": exchange,
            "symbol": symbol,
            "name": name,
            "sector": sector_for(symbol),
            "contracts": len(items),
            "main_contract": main.contract,
            "main_close": main.close,
            "main_change_pct": round(change, 2) if change is not None else None,
            "main_volume": main.volume,
            "main_open_interest": main.open_interest,
            "total_volume": sum_num(x.volume for x in items),
            "total_open_interest": sum_num(x.open_interest for x in items),
            "notional_oi": notional(main, point_value),
            "point_value": point_value,
            "seat": seat_summary,
            "archive_signal": archive_signal,
            "external_signals": external_signals,
            "quality": quality_tag(items, archive_signal, seat_summary, external_signals),
        })

    rows.sort(key=lambda x: (x["exchange"], x["symbol"]))
    return {
        "trade_date": trade_date,
        "count": len(rows),
        "rows": rows,
        "summary": summarize_dataset(rows, archive),
    }


def materialize_variety_dataset(db: Session, trade_date: str) -> dict[str, Any]:
    dataset = build_variety_dataset(db, trade_date)
    now = datetime.utcnow()
    for row in dataset.get("rows", []):
        fact = db.scalar(select(VarietyDailyFact).where(
            VarietyDailyFact.trade_date == trade_date,
            VarietyDailyFact.exchange == row["exchange"],
            VarietyDailyFact.symbol == row["symbol"],
        ))
        if not fact:
            fact = VarietyDailyFact(trade_date=trade_date, exchange=row["exchange"], symbol=row["symbol"], created_at=now)
            db.add(fact)
        archive_signal = row.get("archive_signal") or {}
        seat = row.get("seat") or {}
        quality = row.get("quality") or {}
        fact.name = row.get("name") or ""
        fact.sector = row.get("sector") or ""
        fact.contracts = int(row.get("contracts") or 0)
        fact.main_contract = row.get("main_contract") or ""
        fact.main_close = row.get("main_close")
        fact.main_change_pct = row.get("main_change_pct")
        fact.main_volume = row.get("main_volume")
        fact.main_open_interest = row.get("main_open_interest")
        fact.total_volume = row.get("total_volume")
        fact.total_open_interest = row.get("total_open_interest")
        fact.notional_oi = row.get("notional_oi")
        fact.seat_rank_rows = int(seat.get("rank_rows") or 0)
        fact.seat_net_delta_top20 = seat.get("net_delta_top20")
        fact.archive_net_delta = archive_signal.get("netDelta")
        fact.archive_long_short_ratio = safe_float(archive_signal.get("longShortRatio"))
        fact.archive_long_cr5 = safe_float(archive_signal.get("longCR5"))
        fact.archive_short_cr5 = safe_float(archive_signal.get("shortCR5"))
        fact.quality_daily = quality.get("daily") or "missing"
        fact.quality_seat_rank = quality.get("seat_rank") or "missing"
        fact.quality_archive_signal = quality.get("archive_signal") or "missing"
        fact.fact_json = json.dumps(row, ensure_ascii=False, default=str)
        fact.updated_at = now

    for item in dataset.get("summary", {}).get("exchanges", []):
        cov = db.scalar(select(DailyCoverage).where(DailyCoverage.trade_date == trade_date, DailyCoverage.exchange == item["exchange"]))
        if not cov:
            cov = DailyCoverage(trade_date=trade_date, exchange=item["exchange"], created_at=now)
            db.add(cov)
        cov.varieties = int(item.get("varieties") or 0)
        cov.with_seat_rank = int(item.get("with_seat_rank") or 0)
        cov.with_archive_signal = int(item.get("with_archive_signal") or 0)
        cov.daily_status = "ok" if cov.varieties else "missing"
        cov.seat_status = "ok" if cov.with_seat_rank == cov.varieties and cov.varieties else "partial" if cov.with_seat_rank else "missing"
        cov.archive_status = "ok" if cov.with_archive_signal == cov.varieties and cov.varieties else "partial" if cov.with_archive_signal else "missing"
        cov.message = coverage_message(cov)
        cov.updated_at = now
    db.commit()
    return {"trade_date": trade_date, "count": dataset.get("count", 0), "summary": dataset.get("summary", {})}


def pick_main_contract(items: list[DailyBar]) -> DailyBar:
    return sorted(items, key=lambda x: ((x.volume or 0) * 0.65 + (x.open_interest or 0) * 0.35), reverse=True)[0]


def pick_rows_by_source_priority(rows, source_priority: list[str]) -> dict[str, Any]:
    priority = {name: idx for idx, name in enumerate(source_priority)}
    out: dict[str, Any] = {}
    out_rank: dict[str, int] = {}
    for row in rows:
        symbol = row.symbol.upper()
        rank = priority.get(row.source, len(source_priority))
        if symbol not in out or rank < out_rank[symbol]:
            out[symbol] = row
            out_rank[symbol] = rank
    return out


def summarize_seat_rows(rows: list[SeatRankRow]) -> dict[Any, dict[str, Any]]:
    by_variety: dict[tuple[str, str], list[SeatRankRow]] = defaultdict(list)
    by_name: dict[str, list[SeatRankRow]] = defaultdict(list)
    for r in rows:
        symbol = symbol_from_variety(r.variety)
        if symbol:
            by_variety[(r.exchange, symbol)].append(r)
        by_name[clean_key(r.variety)].append(r)

    out: dict[Any, dict[str, Any]] = {}
    for key, items in by_variety.items():
        out[key] = seat_summary(items)
    for key, items in by_name.items():
        out[key] = seat_summary(items)
    return out


def seat_summary(items: list[SeatRankRow]) -> dict[str, Any]:
    long_delta = sum_num(r.long_open_interest_chg for r in items if (r.rank or 999) <= 20)
    short_delta = sum_num(r.short_open_interest_chg for r in items if (r.rank or 999) <= 20)
    return {
        "rank_rows": len(items),
        "long_delta_top20": long_delta,
        "short_delta_top20": short_delta,
        "net_delta_top20": long_delta - short_delta,
        "top_long_increase": top_party(items, "long"),
        "top_short_increase": top_party(items, "short"),
    }


def top_party(items: list[SeatRankRow], side: str) -> dict[str, Any] | None:
    if side == "long":
        candidates = [r for r in items if r.long_party_name and r.long_open_interest_chg is not None]
        if not candidates:
            return None
        r = max(candidates, key=lambda x: x.long_open_interest_chg or 0)
        return {"party": r.long_party_name, "delta": r.long_open_interest_chg, "value": r.long_open_interest, "contract": r.contract, "rank": r.rank}
    candidates = [r for r in items if r.short_party_name and r.short_open_interest_chg is not None]
    if not candidates:
        return None
    r = max(candidates, key=lambda x: x.short_open_interest_chg or 0)
    return {"party": r.short_party_name, "delta": r.short_open_interest_chg, "value": r.short_open_interest, "contract": r.contract, "rank": r.rank}


def build_archive_index(archive: dict[str, Any]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for section in ["varieties", "net_delta_top", "long_bias", "short_bias", "ratio_extreme", "concentration"]:
        for row in archive.get(section, []) or []:
            compact = {
                "displayName": row.get("displayName") or row.get("name"),
                "exchange": row.get("exchange"),
                "longTotal": row.get("longTotal"),
                "shortTotal": row.get("shortTotal"),
                "longShortRatio": row.get("longShortRatio"),
                "longCR5": row.get("longCR5"),
                "shortCR5": row.get("shortCR5"),
                "longDeltaSum": row.get("longDeltaSum"),
                "shortDeltaSum": row.get("shortDeltaSum"),
                "netDelta": row.get("netDelta"),
                "netDir": row.get("netDir"),
                "topLongByDelta": row.get("topLongByDelta"),
                "topShortByDelta": row.get("topShortByDelta"),
            }
            for key in match_keys("", compact["displayName"]):
                idx.setdefault(key, compact)
    return idx


def first_match(index: dict[Any, dict[str, Any]], keys: list[Any]) -> dict[str, Any] | None:
    for key in keys:
        if key in index:
            return index[key]
    return None


def match_keys(symbol: str, name: str) -> list[str]:
    keys = []
    if symbol:
        keys.append(symbol.upper())
    for text in [name, re.sub(r"[A-Z]+$", "", name or "")]:
        k = clean_key(text)
        if k and k not in keys:
            keys.append(k)
        if "丁二烯" in str(text or "") and "橡胶丁二烯" not in keys:
            keys.append("橡胶丁二烯")
    return keys


def clean_key(text: str | None) -> str:
    s = str(text or "").upper().strip()
    s = re.sub(r"[（(].*?[）)]", "", s)
    # Names like 玻璃FG / 菜粕RM should match Chinese display names, but pure
    # symbols like IC/RB must remain intact.
    if re.search(r"[\u4e00-\u9fff]", s):
        s = re.sub(r"[A-Z]+$", "", s)
    s = s.replace("钢", "").replace("号", "").replace("一", "1").replace("二", "2")
    aliases = {
        "大豆1": "豆1",
        "大豆2": "豆2",
        "黄玉米": "玉米",
        "热轧卷板": "热卷",
        "纸浆": "漂针浆",
        "低硫燃料油": "LU",
        "低硫燃油": "LU",
        "20胶": "NR",
        "丁二烯橡胶": "橡胶丁二烯",
        "铸造铝合金": "AD",
        "阴极铜": "BC",
        "集运指数": "EC",
        "聚苯乙烯": "多晶硅" if s == "聚苯乙烯" else "聚苯乙烯",
    }
    s = aliases.get(s, s)
    return re.sub(r"\s+", "", s)


def symbol_from_variety(variety: str | None) -> str:
    key = clean_key(variety)
    for sym, meta in VARIETY_META_BY_SYMBOL.items():
        if key in {clean_key(sym), clean_key(meta[0]), clean_key(meta[1])}:
            return sym
    # CFFEX varieties usually already equal symbol.
    raw = str(variety or "").upper()
    return raw if raw in VARIETY_META_BY_SYMBOL else ""


def external_signal_item(capital: CapitalFlowDaily | None, basis: BasisDaily | None, warehouse: WarehouseReceiptDaily | None, history: QuheHistoryHolding | None = None) -> dict[str, Any]:
    return {
        "capital_flow": None if not capital else {
            "amount": capital.amount,
            "amount_yi": round((capital.amount or 0) / 100000000, 2),
            "product_name": capital.product_name,
            "source_time": capital.source_time,
            "source": capital.source,
        },
        "basis": None if not basis else {
            "spot_price": basis.spot_price,
            "main_price": basis.main_price,
            "basis": basis.basis,
            "basis_rate": basis.basis_rate,
            "highest": basis.highest,
            "lowest": basis.lowest,
            "average": basis.average,
            "source": basis.source,
        },
        "warehouse_receipt": None if not warehouse else {
            "receipt_number": warehouse.receipt_number,
            "increase_number": warehouse.increase_number,
            "increase_ratio": warehouse.increase_ratio,
            "hand_number": warehouse.hand_number,
            "source": warehouse.source,
        },
        "history_holding": None if not history else {
            "symbol_code": history.symbol_code,
            "long_total": history.long_total,
            "short_total": history.short_total,
            "net_total": history.net_total,
            "source": history.source,
        },
    }


def quality_tag(items: list[DailyBar], archive_signal: dict[str, Any] | None, seat_summary_: dict[str, Any], external_signals: dict[str, Any] | None = None) -> dict[str, Any]:
    external_signals = external_signals or {}
    return {
        "daily": "ok" if items else "missing",
        "seat_rank": "ok" if seat_summary_.get("rank_rows") else "missing",
        "archive_signal": "ok" if archive_signal else "missing",
        "capital_flow": "ok" if external_signals.get("capital_flow") else "missing",
        "basis": "ok" if external_signals.get("basis") else "missing",
        "warehouse_receipt": "ok" if external_signals.get("warehouse_receipt") else "missing",
        "history_holding": "ok" if external_signals.get("history_holding") else "missing",
    }


def summarize_dataset(rows: list[dict[str, Any]], archive: dict[str, Any]) -> dict[str, Any]:
    by_exchange: dict[str, dict[str, int]] = defaultdict(lambda: {"varieties": 0, "with_seat_rank": 0, "with_archive_signal": 0})
    for r in rows:
        bucket = by_exchange[r["exchange"]]
        bucket["varieties"] += 1
        if r["quality"]["seat_rank"] == "ok":
            bucket["with_seat_rank"] += 1
        if r["quality"]["archive_signal"] == "ok":
            bucket["with_archive_signal"] += 1
    return {
        "exchanges": [{"exchange": k, **v} for k, v in sorted(by_exchange.items())],
        "archive_status": archive.get("status"),
        "archive_count": archive.get("count", 0),
    }


def safe_float_value(value: Any) -> float:
    try:
        f = float(value)
        return f if not (f != f) else 0.0  # NaN guard
    except (TypeError, ValueError):
        return 0.0


def sum_num(values) -> float:
    return float(sum(safe_float_value(v) for v in values))


def notional(bar: DailyBar, point_value: float | None) -> float | None:
    if point_value is None:
        return None
    try:
        close = float(bar.close)
        oi = float(bar.open_interest)
        if not close or not oi:
            return None
        return round(point_value * close * oi, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def coverage_message(cov: DailyCoverage) -> str:
    notes = []
    if cov.daily_status != "ok":
        notes.append("日行情缺失")
    if cov.seat_status != "ok":
        notes.append(f"席位覆盖 {cov.with_seat_rank}/{cov.varieties}")
    if cov.archive_status != "ok":
        notes.append(f"结构信号覆盖 {cov.with_archive_signal}/{cov.varieties}")
    return "；".join(notes) if notes else "覆盖完整"
