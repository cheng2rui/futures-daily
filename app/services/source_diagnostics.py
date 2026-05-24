from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import CrawlerRun, DataGap, SourceFile
from app.services.coverage_matrix import build_coverage_matrix
from app.services.error_classifier import classify_record_error, summarize_categories
from app.services.raw_archive import source_file_item

WEAK_EXCHANGES = ("DCE", "INE")


def diagnose_weak_sources(db: Session, trade_date: str, exchanges: list[str] | None = None) -> dict[str, Any]:
    selected = [x.upper() for x in (exchanges or list(WEAK_EXCHANGES))]
    matrix = build_coverage_matrix(db, trade_date, sync_gaps=False)
    rows_by_exchange = {row["exchange"]: row for row in matrix.get("rows", [])}
    return {
        "trade_date": trade_date,
        "exchanges": [diagnose_exchange(db, trade_date, ex, rows_by_exchange.get(ex, {})) for ex in selected],
    }


def diagnose_exchange(db: Session, trade_date: str, exchange: str, coverage_row: dict[str, Any]) -> dict[str, Any]:
    cells = coverage_row.get("cells") or {}
    issues = []
    actions = []

    for kind, cell in cells.items():
        status = cell.get("status")
        if status in {"missing", "failed", "partial"}:
            issues.append(issue_item(db, trade_date, exchange, kind, cell))
        if kind in {"daily", "seat_rank"} and status in {"missing", "failed", "partial"}:
            actions.append({"type": "recollect", "kind": kind, "endpoint": f"POST /api/reports/{trade_date}/recollect?exchange={exchange}&kinds={kind}"})
        if status == "not_supported":
            issues.append({
                "kind": kind,
                "status": status,
                "severity": "info",
                "message": cell.get("message") or "不适用",
                "latest_run": None,
                "latest_gap": None,
                "error_category": classify_record_error(message=cell.get("message"), status=status, kind=kind),
                "latest_archive": None,
            })

    if exchange == "DCE":
        actions.append({"type": "probe", "kind": "daily", "note": "DCE 日行情优先 AkShare 官方；失败时使用 Sina fallback，需关注是否为连续合约。"})
        actions.append({"type": "external_source", "kind": "seat_rank", "note": "DCE 席位暂无稳定公开 fallback；建议后续接 Tushare Pro / Wind / iFinD 授权源。"})
    if exchange == "INE":
        actions.append({"type": "adapter", "kind": "seat_rank", "note": "INE 席位 adapter 未实现；若找到官方披露接口，可先接 raw archive，再接 parser replay。"})

    category_summary = summarize_categories(issues)
    return {
        "exchange": exchange,
        "status": coverage_row.get("status") or "unknown",
        "summary": coverage_row.get("summary") or "暂无覆盖矩阵记录",
        "error_summary": category_summary,
        "issues": issues,
        "actions": actions,
    }


def issue_item(db: Session, trade_date: str, exchange: str, kind: str, cell: dict[str, Any]) -> dict[str, Any]:
    run = latest_run(db, trade_date, exchange, kind)
    gap = latest_gap(db, trade_date, exchange, kind)
    archive = latest_archive(db, trade_date, exchange, kind)
    category = classify_record_error(
        error=(run.error if run else "") or (archive.error if archive else ""),
        message=(gap.message if gap else "") or cell.get("message"),
        status=cell.get("status"),
        kind=kind,
        source=(run.source if run else archive.source if archive else ""),
    )
    return {
        "kind": kind,
        "status": cell.get("status"),
        "severity": "error" if kind in {"daily", "seat_rank"} and cell.get("status") == "failed" else "warning",
        "message": cell.get("message") or "数据缺失",
        "error_category": category,
        "latest_run": run_item(run) if run else None,
        "latest_gap": gap_item(gap) if gap else None,
        "latest_archive": source_file_item(archive) if archive else None,
    }


def latest_run(db: Session, trade_date: str, exchange: str, kind: str) -> CrawlerRun | None:
    return db.scalar(
        select(CrawlerRun)
        .where(CrawlerRun.trade_date == trade_date, CrawlerRun.exchange == exchange, CrawlerRun.kind == kind)
        .order_by(desc(CrawlerRun.started_at))
        .limit(1)
    )


def latest_gap(db: Session, trade_date: str, exchange: str, kind: str) -> DataGap | None:
    return db.scalar(
        select(DataGap)
        .where(DataGap.trade_date == trade_date, DataGap.exchange == exchange, DataGap.kind == kind)
        .order_by(desc(DataGap.created_at))
        .limit(1)
    )


def latest_archive(db: Session, trade_date: str, exchange: str, kind: str) -> SourceFile | None:
    return db.scalar(
        select(SourceFile)
        .where(SourceFile.trade_date == trade_date, SourceFile.exchange == exchange, SourceFile.kind == kind)
        .order_by(desc(SourceFile.created_at))
        .limit(1)
    )


def run_item(row: CrawlerRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "status": row.status,
        "rows": row.rows,
        "saved": row.saved,
        "error": row.error,
        "error_category": classify_record_error(error=row.error, status=row.status, kind=row.kind, source=row.source),
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def gap_item(row: DataGap) -> dict[str, Any]:
    return {
        "id": row.id,
        "severity": row.severity,
        "status": row.status,
        "rows": row.rows,
        "message": row.message,
        "created_at": row.created_at,
        "resolved_at": row.resolved_at,
    }
