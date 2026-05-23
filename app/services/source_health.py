from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import CrawlerRun, DataGap, SourceFile
from app.services.raw_archive import source_file_item
from app.sources.registry import list_provider_capabilities

KNOWN_SOURCES = ["akshare", "dce_sina_fallback", "quheqihuo", "akshare_official", "akshare_100ppi"]


def build_source_health(db: Session, trade_date: str) -> dict[str, Any]:
    sources = sorted(set(KNOWN_SOURCES) | set(source_names(db, trade_date)))
    provider_caps = {row["name"]: row for row in list_provider_capabilities()}
    rows = [source_health_item(db, trade_date, source, provider_caps.get(source)) for source in sources]
    rows.sort(key=lambda x: (-x["score"], x["source"]))
    return {
        "trade_date": trade_date,
        "summary": health_summary(rows),
        "sources": rows,
        "provider_capabilities": list_provider_capabilities(),
    }


def source_names(db: Session, trade_date: str) -> list[str]:
    names = set()
    for row in db.scalars(select(SourceFile.source).where(SourceFile.trade_date == trade_date)).all():
        if row:
            names.add(str(row))
    for row in db.scalars(select(CrawlerRun.source).where(CrawlerRun.trade_date == trade_date)).all():
        if row:
            names.add(str(row))
    return sorted(names)


def source_health_item(db: Session, trade_date: str, source: str, provider_cap: dict[str, Any] | None) -> dict[str, Any]:
    runs = list(
        db.scalars(
            select(CrawlerRun)
            .where(CrawlerRun.trade_date == trade_date, CrawlerRun.source == source)
            .order_by(desc(CrawlerRun.started_at))
        ).all()
    )
    archives = list(
        db.scalars(
            select(SourceFile)
            .where(SourceFile.trade_date == trade_date, SourceFile.source == source)
            .order_by(desc(SourceFile.created_at))
        ).all()
    )
    gaps = list(db.scalars(select(DataGap).where(DataGap.trade_date == trade_date)).all())
    source_gaps = [g for g in gaps if source_matches_gap(source, g.kind)]

    total_runs = len(runs)
    success_runs = sum(1 for r in runs if r.status == "success")
    partial_runs = sum(1 for r in runs if r.status == "partial")
    failed_runs = sum(1 for r in runs if r.status == "failed")
    open_gaps = sum(1 for g in source_gaps if g.status == "open")
    resolved_gaps = sum(1 for g in source_gaps if g.status == "resolved")
    archive_count = len(archives)
    total_rows = sum(int(a.rows or 0) for a in archives)
    distinct_kinds = len({a.kind for a in archives})
    distinct_exchanges = len({a.exchange for a in archives})
    latest_error = next((r.error for r in runs if r.error), next((a.error for a in archives if a.error), ""))
    success_rate = round(success_runs / total_runs * 100, 1) if total_runs else 0.0

    archive_score = min(20, archive_count * 2)
    kind_score = min(20, distinct_kinds * 4)
    volume_score = min(20, total_rows // 20)
    run_score = round(success_rate * 0.45 + (100 if total_runs and failed_runs == 0 else 70 if success_runs else 20) * 0.25, 1)
    gap_penalty = min(30, open_gaps * 5 + max(0, resolved_gaps - open_gaps))
    error_penalty = min(25, failed_runs * 5 + partial_runs * 2)
    score = round(clamp(run_score + archive_score + kind_score + volume_score - gap_penalty - error_penalty), 1)
    status = "good" if score >= 75 else "warn" if score >= 45 else "bad"

    return {
        "source": source,
        "provider_status": provider_cap.get("status") if provider_cap else "unknown",
        "provider_note": provider_cap.get("note") if provider_cap else "",
        "score": score,
        "status": status,
        "summary": source_summary(source, score, total_runs, success_runs, failed_runs, archive_count, open_gaps),
        "runs_total": total_runs,
        "runs_success": success_runs,
        "runs_partial": partial_runs,
        "runs_failed": failed_runs,
        "success_rate": success_rate,
        "archives_count": archive_count,
        "archive_rows": total_rows,
        "distinct_kinds": distinct_kinds,
        "distinct_exchanges": distinct_exchanges,
        "open_gaps": open_gaps,
        "resolved_gaps": resolved_gaps,
        "latest_error": latest_error,
        "latest_runs": [run_item(r) for r in runs[:5]],
        "latest_archives": [source_file_item(a) for a in archives[:5]],
    }


def source_matches_gap(source: str, kind: str) -> bool:
    if source == "akshare":
        return kind in {"daily", "seat_rank"}
    if source == "dce_sina_fallback":
        return kind == "daily"
    if source == "quheqihuo":
        return kind in {"capital_flow", "basis", "warehouse_receipt", "quhe_contract_tree", "quhe_history_holding", "seat_rank_fallback"}
    if source == "akshare_official":
        return kind in {"warehouse_receipt", "warehouse_receipt_official"}
    if source == "akshare_100ppi":
        return kind in {"basis", "basis_100ppi"}
    return True


def source_summary(source: str, score: float, total_runs: int, success_runs: int, failed_runs: int, archive_count: int, open_gaps: int) -> str:
    parts = [f"评分 {score}"]
    if total_runs:
        parts.append(f"运行 {success_runs}/{total_runs} 成功")
    if archive_count:
        parts.append(f"归档 {archive_count} 个")
    if open_gaps:
        parts.append(f"开放缺口 {open_gaps} 个")
    if failed_runs:
        parts.append(f"失败 {failed_runs} 次")
    return f"{source}：" + "；".join(parts)


def health_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    good = sum(1 for r in rows if r["status"] == "good")
    warn = sum(1 for r in rows if r["status"] == "warn")
    bad = sum(1 for r in rows if r["status"] == "bad")
    avg = round(sum(float(r["score"]) for r in rows) / total, 1) if total else 0
    return {
        "total_sources": total,
        "good_sources": good,
        "warn_sources": warn,
        "bad_sources": bad,
        "average_score": avg,
        "top_sources": [r["source"] for r in rows[:3]],
        "weak_sources": [r["source"] for r in rows if r["status"] == "bad"],
        "status": "good" if bad == 0 and warn <= 1 else "warn" if bad == 0 else "bad",
        "summary": f"来源 {total} 个，健康 {good} 个，预警 {warn} 个，异常 {bad} 个，平均分 {avg}",
    }


def run_item(row: CrawlerRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "trade_date": row.trade_date,
        "exchange": row.exchange,
        "kind": row.kind,
        "status": row.status,
        "rows": row.rows,
        "saved": row.saved,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
