from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.metadata.variety_meta import get_exchange_code
from app.models import (
    BasisDaily,
    CapitalFlowDaily,
    CrawlerRun,
    DailyBar,
    DataGap,
    MarketSnapshot,
    SeatRankRow,
    VarietyDailyFact,
    WarehouseReceiptDaily,
)
from app.services.event_calendar import build_event_calendar

CORE_KINDS = ("daily", "seat_rank")
ENHANCEMENT_KINDS = ("archive_signal", "capital_flow", "basis", "warehouse_receipt", "event_calendar")
MATRIX_KINDS = CORE_KINDS + ENHANCEMENT_KINDS

KIND_LABELS = {
    "daily": "日行情",
    "seat_rank": "席位",
    "archive_signal": "席位归档",
    "capital_flow": "资金流",
    "basis": "基差",
    "warehouse_receipt": "仓单",
    "event_calendar": "事件日历",
}

NOT_SUPPORTED_BY_EXCHANGE = {
    "basis": {"CFFEX"},
    "warehouse_receipt": {"CFFEX"},
}


def build_coverage_matrix(db: Session, trade_date: str, *, sync_gaps: bool = False) -> dict[str, Any]:
    """Build an exchange × data-kind coverage matrix for a trading day.

    This is deliberately exchange-level, not variety-level: it answers the daily
    operations question first — which exchanges have usable data, which are
    missing, and which gaps should be visible before a report is trusted.
    """
    exchanges = [str(x).upper() for x in get_settings().exchanges.enabled]
    run_index = latest_runs(db, trade_date)
    snapshot_index = latest_snapshots(db, trade_date)

    counts = {
        "daily": grouped_count(db, DailyBar.exchange, DailyBar.trade_date == trade_date),
        "seat_rank": grouped_count(db, SeatRankRow.exchange, SeatRankRow.trade_date == trade_date),
        "archive_signal": grouped_count(
            db,
            VarietyDailyFact.exchange,
            VarietyDailyFact.trade_date == trade_date,
            VarietyDailyFact.quality_archive_signal == "ok",
        ),
        "capital_flow": external_counts(db.scalars(select(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date))),
        "basis": external_counts(db.scalars(select(BasisDaily).where(BasisDaily.trade_date == trade_date))),
        "warehouse_receipt": external_counts(db.scalars(select(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date))),
    }
    event_calendar = build_event_calendar(trade_date)
    event_count = int(event_calendar.get("summary", {}).get("count") or 0)

    rows: list[dict[str, Any]] = []
    totals = {kind: defaultdict(int) for kind in MATRIX_KINDS}
    for exchange in exchanges:
        cells: dict[str, dict[str, Any]] = {}
        for kind in MATRIX_KINDS:
            if kind == "event_calendar":
                cell = event_cell(event_count)
            elif exchange in NOT_SUPPORTED_BY_EXCHANGE.get(kind, set()):
                cell = status_cell("not_supported", 0, "不适用", "-")
            elif kind == "seat_rank" and counts["seat_rank"].get(exchange, 0) <= 0:
                fallback = fallback_cell(exchange, run_index, snapshot_index)
                cell = fallback if fallback["status"] == "fallback" else source_cell(kind, exchange, counts, run_index, snapshot_index)
            else:
                cell = source_cell(kind, exchange, counts, run_index, snapshot_index)
            cells[kind] = cell
            totals[kind][cell["status"]] += 1

        row_status = row_overall_status(cells)
        rows.append({
            "exchange": exchange,
            "status": row_status,
            "cells": cells,
            "summary": row_summary(cells),
        })

    summary = matrix_summary(rows, totals, exchanges)
    result = {
        "trade_date": trade_date,
        "kinds": [{"key": kind, "label": KIND_LABELS[kind]} for kind in MATRIX_KINDS],
        "rows": rows,
        "summary": summary,
        "event_calendar": {
            "count": event_count,
            "next_event": event_calendar.get("summary", {}).get("next_event"),
        },
    }
    if sync_gaps:
        sync_coverage_gaps(db, trade_date, rows)
    return result


def grouped_count(db: Session, group_col, *where) -> dict[str, int]:
    stmt = select(group_col, func.count()).where(*where).group_by(group_col)
    return {str(k).upper(): int(v or 0) for k, v in db.execute(stmt).all() if k}


def external_counts(rows: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for row in rows:
        symbol = str(getattr(row, "symbol", "") or "").upper()
        exchange = get_exchange_code(symbol, "")
        if exchange:
            out[exchange] += 1
    return dict(out)


def latest_runs(db: Session, trade_date: str) -> dict[tuple[str, str], CrawlerRun]:
    rows = db.scalars(select(CrawlerRun).where(CrawlerRun.trade_date == trade_date).order_by(desc(CrawlerRun.started_at))).all()
    out: dict[tuple[str, str], CrawlerRun] = {}
    for row in rows:
        out.setdefault((row.exchange, row.kind), row)
    return out


def latest_snapshots(db: Session, trade_date: str) -> dict[tuple[str, str], MarketSnapshot]:
    rows = db.scalars(select(MarketSnapshot).where(MarketSnapshot.trade_date == trade_date).order_by(desc(MarketSnapshot.created_at))).all()
    out: dict[tuple[str, str], MarketSnapshot] = {}
    for row in rows:
        out.setdefault((row.exchange, row.snapshot_type), row)
    return out


def source_cell(kind: str, exchange: str, counts: dict[str, dict[str, int]], run_index: dict, snapshot_index: dict) -> dict[str, Any]:
    rows = int(counts.get(kind, {}).get(exchange, 0) or 0)
    run = run_index.get((exchange, kind))
    snap = snapshot_index.get((exchange, kind))
    source = run.source if run else snap.source if snap else "-"
    error = run.error if run and run.error else snapshot_error(snap)
    if rows > 0 and not error:
        return status_cell("ok", rows, "已入库", source)
    if rows > 0 and error:
        return status_cell("partial", rows, str(error), source)
    if run and run.status == "failed":
        return status_cell("failed", 0, run.error or "采集失败", source)
    if error:
        return status_cell("failed", 0, str(error), source)
    return status_cell("missing", 0, "未采集", source)


def fallback_cell(exchange: str, run_index: dict, snapshot_index: dict) -> dict[str, Any]:
    run = run_index.get((exchange, "seat_rank_fallback"))
    snap = snapshot_index.get((exchange, "seat_rank_fallback"))
    rows = int((run.saved or run.rows) if run else snapshot_rows(snap)) if (run or snap) else 0
    error = run.error if run and run.error else snapshot_error(snap)
    source = run.source if run else snap.source if snap else "-"
    if rows > 0 and not error:
        return status_cell("fallback", rows, "席位使用备用源", source)
    if run and run.status == "failed":
        return status_cell("failed", 0, run.error or "席位备用源失败", source)
    return status_cell("missing", 0, "未采集", source)


def event_cell(count: int) -> dict[str, Any]:
    if count > 0:
        return status_cell("ok", count, "规则/手动事件可用", "local")
    return status_cell("missing", 0, "近期暂无事件", "local")


def status_cell(status: str, rows: int, message: str, source: str) -> dict[str, Any]:
    return {"status": status, "rows": rows, "message": message, "source": source}


def snapshot_rows(snap: MarketSnapshot | None) -> int:
    if not snap:
        return 0
    try:
        payload = json.loads(snap.raw_json or "{}")
    except Exception:
        return 0
    return int(payload.get("row_count") or len(payload.get("rows") or []) or 0)


def snapshot_error(snap: MarketSnapshot | None) -> str:
    if not snap:
        return ""
    try:
        payload = json.loads(snap.raw_json or "{}")
    except Exception:
        return ""
    return str(payload.get("error") or "")


def row_overall_status(cells: dict[str, dict[str, Any]]) -> str:
    core = [cells[k]["status"] for k in CORE_KINDS]
    if all(x in {"ok", "fallback"} for x in core):
        if any(c["status"] in {"missing", "failed", "partial"} for k, c in cells.items() if k in ENHANCEMENT_KINDS):
            return "partial"
        return "ok"
    if any(x in {"ok", "fallback", "partial"} for x in core):
        return "partial"
    return "failed"


def row_summary(cells: dict[str, dict[str, Any]]) -> str:
    bad = [KIND_LABELS[k] for k, c in cells.items() if c["status"] in {"missing", "failed", "partial"} and k != "event_calendar"]
    fallback = [KIND_LABELS[k] for k, c in cells.items() if c["status"] == "fallback"]
    if not bad and not fallback:
        return "核心与增强数据齐全"
    parts = []
    if fallback:
        parts.append("备用：" + "、".join(fallback))
    if bad:
        parts.append("缺口：" + "、".join(bad[:4]))
    return "；".join(parts)


def matrix_summary(rows: list[dict[str, Any]], totals: dict[str, dict[str, int]], exchanges: list[str]) -> dict[str, Any]:
    total = len(exchanges)
    ok_rows = sum(1 for r in rows if r["status"] == "ok")
    partial_rows = sum(1 for r in rows if r["status"] == "partial")
    failed_rows = sum(1 for r in rows if r["status"] == "failed")
    core_cells = total * len(CORE_KINDS)
    core_ok = sum(1 for r in rows for k in CORE_KINDS if r["cells"][k]["status"] in {"ok", "fallback"})
    all_supported_cells = sum(1 for r in rows for c in r["cells"].values() if c["status"] != "not_supported")
    all_ok = sum(1 for r in rows for c in r["cells"].values() if c["status"] in {"ok", "fallback"})
    return {
        "status": "ok" if ok_rows == total else "partial" if ok_rows + partial_rows else "failed",
        "exchanges": total,
        "ok_exchanges": ok_rows,
        "partial_exchanges": partial_rows,
        "failed_exchanges": failed_rows,
        "core_coverage_pct": round(core_ok / core_cells * 100, 1) if core_cells else 0,
        "overall_coverage_pct": round(all_ok / all_supported_cells * 100, 1) if all_supported_cells else 0,
        "by_kind": {kind: dict(status_counts) for kind, status_counts in totals.items()},
    }


def sync_coverage_gaps(db: Session, trade_date: str, rows: list[dict[str, Any]]) -> None:
    now = datetime.utcnow()
    for row in rows:
        exchange = row["exchange"]
        for kind, cell in row["cells"].items():
            if kind == "event_calendar" or cell["status"] == "not_supported":
                continue
            gap = db.scalar(select(DataGap).where(DataGap.trade_date == trade_date, DataGap.exchange == exchange, DataGap.kind == kind))
            if cell["status"] in {"ok", "fallback"}:
                if gap and gap.status == "open":
                    gap.status = "resolved"
                    gap.rows = int(cell.get("rows") or 0)
                    gap.message = "resolved by coverage check"
                    gap.resolved_at = now
                continue
            if not gap:
                gap = DataGap(trade_date=trade_date, exchange=exchange, kind=kind, created_at=now)
                db.add(gap)
            gap.status = "open"
            gap.severity = "error" if kind in CORE_KINDS or cell["status"] == "failed" else "warning"
            gap.rows = int(cell.get("rows") or 0)
            gap.message = cell.get("message") or "missing"
            gap.resolved_at = None
    db.commit()
