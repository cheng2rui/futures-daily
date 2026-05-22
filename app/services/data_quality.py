from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CrawlerRun, DataGap, MarketSnapshot


SUMMARY_KINDS = ("daily", "seat_rank", "seat_rank_fallback")


def build_data_quality(db: Session, trade_date: str) -> dict[str, Any]:
    expected = list(get_settings().exchanges.enabled)
    snapshots = list(
        db.scalars(
            select(MarketSnapshot)
            .where(MarketSnapshot.trade_date == trade_date)
            .order_by(desc(MarketSnapshot.created_at))
        )
    )
    latest: dict[tuple[str, str], MarketSnapshot] = {}
    for snap in snapshots:
        latest.setdefault((snap.exchange, snap.snapshot_type), snap)

    gaps = list(db.scalars(select(DataGap).where(DataGap.trade_date == trade_date)))
    latest_gap: dict[tuple[str, str], DataGap] = {}
    for gap in gaps:
        latest_gap.setdefault((gap.exchange, gap.kind), gap)

    runs = list(
        db.scalars(
            select(CrawlerRun)
            .where(CrawlerRun.trade_date == trade_date)
            .order_by(desc(CrawlerRun.started_at))
        )
    )
    latest_run: dict[tuple[str, str], CrawlerRun] = {}
    for run in runs:
        latest_run.setdefault((run.exchange, run.kind), run)

    rows: list[dict[str, Any]] = []
    daily_ok = 0
    daily_any = 0
    seat_ok = 0
    seat_any = 0
    fallback_used = 0
    failed_exchanges: list[str] = []
    partial_exchanges: list[str] = []
    missing_exchanges: list[str] = []

    for exchange in expected:
        daily = _snap_status(latest.get((exchange, "daily")))
        seat = _snap_status(latest.get((exchange, "seat_rank")))
        fallback = _snap_status(latest.get((exchange, "seat_rank_fallback")))
        if not fallback["rows"]:
            fallback = _run_status(latest_run.get((exchange, "seat_rank_fallback")))
        gap_note = _gap_note(latest_gap, exchange)
        unrecoverable_kinds = _unrecoverable_kinds(exchange, daily, seat, fallback)
        exchange_note = _exchange_note(daily, seat, fallback, unrecoverable_kinds)
        if fallback["ok"] and daily["ok"]:
            gap_note = ""

        has_daily = daily["rows"] > 0
        has_seat = seat["rows"] > 0
        has_fallback = fallback["rows"] > 0

        if has_daily:
            daily_any += 1
        if daily["ok"]:
            daily_ok += 1

        if has_seat or has_fallback:
            seat_any += 1
        if seat["ok"]:
            seat_ok += 1
        if has_fallback:
            fallback_used += 1

        if not has_daily and not has_seat and not has_fallback:
            exchange_status = "failed"
            missing_exchanges.append(exchange)
        elif daily["ok"] and (seat["ok"] or fallback["ok"]):
            exchange_status = "ok"
        elif has_daily or has_seat or has_fallback:
            exchange_status = "partial"
            partial_exchanges.append(exchange)
        else:
            exchange_status = "failed"
            failed_exchanges.append(exchange)

        if exchange_status == "failed" and exchange not in missing_exchanges:
            failed_exchanges.append(exchange)

        rows.append(
            {
                "exchange": exchange,
                "daily": daily,
                "seat_rank": seat,
                "seat_rank_fallback": fallback,
                "status": exchange_status,
                "recoverable": not unrecoverable_kinds,
                "unrecoverable_kinds": unrecoverable_kinds,
                "note": exchange_note if unrecoverable_kinds else gap_note or exchange_note,
            }
        )

    total = len(expected)
    overall_ok = sum(1 for x in rows if x["status"] == "ok")
    overall_partial = sum(1 for x in rows if x["status"] == "partial")
    status = "ok" if overall_ok == total else "partial" if (overall_ok + overall_partial) else "failed"
    daily_coverage_pct = round(daily_any / total * 100, 1) if total else 0
    seat_coverage_pct = round(seat_any / total * 100, 1) if total else 0
    availability_pct = round((daily_any + seat_any) / (total * 2) * 100, 1) if total else 0
    # Headline quality score rewards complete official data, while fallback counts
    # as half-weight. This avoids showing “100%” when important sources failed
    # but were partially rescued by fallback.
    overall_coverage_pct = round((daily_ok + seat_ok + fallback_used * 0.5) / (total * 2) * 100, 1) if total else 0

    unrecoverable_exchanges = [x["exchange"] for x in rows if x.get("unrecoverable_kinds")]
    summary = build_summary(
        total=total,
        daily_any=daily_any,
        daily_ok=daily_ok,
        seat_any=seat_any,
        seat_ok=seat_ok,
        fallback_used=fallback_used,
        failed_exchanges=failed_exchanges,
        partial_exchanges=partial_exchanges,
        missing_exchanges=missing_exchanges,
        unrecoverable_exchanges=unrecoverable_exchanges,
    )

    return {
        "trade_date": trade_date,
        "status": status,
        "expected": total,
        "daily_ok": daily_ok,
        "daily_available": daily_any,
        "seat_ok": seat_ok,
        "seat_available": seat_any,
        "fallback_used": fallback_used,
        "daily_coverage_pct": daily_coverage_pct,
        "seat_coverage_pct": seat_coverage_pct,
        "coverage_pct": overall_coverage_pct,
        "overall_coverage_pct": overall_coverage_pct,
        "availability_pct": availability_pct,
        "failed_exchanges": failed_exchanges,
        "partial_exchanges": partial_exchanges,
        "missing_exchanges": missing_exchanges,
        "unrecoverable_exchanges": unrecoverable_exchanges,
        "summary": summary,
        "exchanges": rows,
    }


def _snap_status(snap: MarketSnapshot | None) -> dict[str, Any]:
    if not snap:
        return {"ok": False, "rows": 0, "error": "not_collected", "source": "-"}
    try:
        payload = json.loads(snap.raw_json or "{}")
    except Exception:
        payload = {}
    rows = payload.get("row_count")
    if rows is None:
        rows = len(payload.get("rows") or [])
    error = payload.get("error")
    return {
        "ok": bool(rows) and not error,
        "rows": rows or 0,
        "error": error,
        "source": snap.source,
    }


def _run_status(run: CrawlerRun | None) -> dict[str, Any]:
    if not run:
        return {"ok": False, "rows": 0, "error": "not_collected", "source": "-"}
    rows = run.saved or run.rows or 0
    error = run.error or None
    return {"ok": bool(rows) and not error, "rows": rows, "error": error, "source": run.source}


def _gap_note(latest_gap: dict[tuple[str, str], DataGap], exchange: str) -> str:
    parts = []
    for kind in SUMMARY_KINDS:
        gap = latest_gap.get((exchange, kind))
        if gap and gap.status == "open":
            parts.append(f"{kind}:{gap.message[:48]}")
    return "；".join(parts)


def _unrecoverable_kinds(exchange: str, daily: dict[str, Any], seat: dict[str, Any], fallback: dict[str, Any]) -> list[str]:
    seat_error = str(seat.get("error") or fallback.get("error") or "").lower()
    if exchange == "DCE" and not seat["rows"] and "fallback unavailable" in seat_error:
        return ["seat_rank"]
    return []


def _exchange_note(daily: dict[str, Any], seat: dict[str, Any], fallback: dict[str, Any], unrecoverable_kinds: list[str] | None = None) -> str:
    if unrecoverable_kinds:
        return "席位暂无公开可用备用源，标记为不可恢复；需要官方恢复或商业数据源。"
    if not daily["rows"] and not seat["rows"] and not fallback["rows"]:
        return "行情/席位均未采集"
    if daily["rows"] and not daily["ok"]:
        return f"日行情异常：{daily.get('error') or 'unknown'}"
    if fallback["ok"]:
        return "席位使用 fallback 补充"
    if seat["rows"] and not seat["ok"]:
        return f"席位异常：{seat.get('error') or 'unknown'}"
    if daily["ok"] and seat["ok"]:
        return "-"
    return "部分数据待确认"


def build_summary(
    *,
    total: int,
    daily_any: int,
    daily_ok: int,
    seat_any: int,
    seat_ok: int,
    fallback_used: int,
    failed_exchanges: list[str],
    partial_exchanges: list[str],
    missing_exchanges: list[str],
    unrecoverable_exchanges: list[str] | None = None,
) -> str:
    parts = [
        f"交易所 {total} 家",
        f"日行情覆盖 {daily_any}/{total}，完整 {daily_ok}/{total}",
        f"席位覆盖 {seat_any}/{total}，完整 {seat_ok}/{total}",
    ]
    if fallback_used:
        parts.append(f"fallback {fallback_used} 家")
    if partial_exchanges:
        parts.append("部分：" + "、".join(partial_exchanges[:4]))
    if failed_exchanges:
        parts.append("失败：" + "、".join(failed_exchanges[:4]))
    if missing_exchanges:
        parts.append("缺失：" + "、".join(missing_exchanges[:4]))
    if unrecoverable_exchanges:
        parts.append("不可恢复：" + "、".join(unrecoverable_exchanges[:4]))
    return "；".join(parts)
