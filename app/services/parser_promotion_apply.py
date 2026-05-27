from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerRun, DataGap, SeatRankRow, SourceFile
from app.services.parser_promotion_preview import build_promotion_preview


def expected_confirm_token(source_file_id: int) -> str:
    return f"PROMOTE-{source_file_id}"


def apply_promotion_preview(
    db: Session,
    source_file: SourceFile,
    *,
    confirm: str | None = None,
    sample_limit: int = 500,
) -> dict[str, Any]:
    """Guarded, idempotent promotion from browser-probe parser preview to seat_rank_rows.

    This is intentionally conservative:
    - requires the same promotion guard as preview;
    - requires an explicit confirm token, so random clicks/API calls cannot write;
    - appends only missing exact tuples instead of deleting existing exchange data;
    - marks inserted rows with source_file_id/record_id in raw_json for audit.
    """
    preview = build_promotion_preview(source_file, sample_limit=sample_limit)
    token = expected_confirm_token(source_file.id)
    if confirm != token:
        return {
            **preview,
            "status": "blocked",
            "would_write": False,
            "inserted": 0,
            "skipped": 0,
            "confirm_required": token,
            "message": f"Confirm token required: {token}. No database rows were written.",
        }
    if not preview.get("promotion_guard", {}).get("allowed"):
        return {
            **preview,
            "status": "blocked",
            "would_write": False,
            "inserted": 0,
            "skipped": 0,
            "message": "Guard BLOCKED: promotion not applied; no database rows were written.",
        }

    rows = preview.get("preview_rows") or []
    run = CrawlerRun(
        trade_date=source_file.trade_date,
        exchange=source_file.exchange,
        kind="seat_rank",
        source=f"promotion:{source_file.source or source_file.kind}",
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()

    inserted = 0
    skipped = 0
    for row in rows:
        if _seat_row_exists(db, row):
            skipped += 1
            continue
        db.add(_seat_rank_from_preview(row))
        inserted += 1

    run.rows = len(rows)
    run.saved = inserted
    run.error = "" if inserted else "all preview rows already existed"
    run.status = "success" if inserted else "partial"
    run.finished_at = datetime.utcnow()
    _update_gap_after_promotion(db, source_file, inserted)
    db.commit()

    return {
        **preview,
        "dry_run": False,
        "would_write": True,
        "status": "applied" if inserted else "noop",
        "inserted": inserted,
        "skipped": skipped,
        "crawler_run_id": run.id,
        "message": f"Promotion applied: inserted {inserted}, skipped {skipped}." if inserted else f"Promotion noop: skipped {skipped} existing rows.",
    }


def _seat_row_exists(db: Session, row: dict[str, Any]) -> bool:
    stmt = select(SeatRankRow.id).where(
        SeatRankRow.trade_date == str(row.get("trade_date") or ""),
        SeatRankRow.exchange == str(row.get("exchange") or ""),
        SeatRankRow.variety == str(row.get("variety") or ""),
        SeatRankRow.contract == str(row.get("contract") or ""),
        SeatRankRow.rank == row.get("rank"),
        SeatRankRow.vol_party_name == str(row.get("vol_party_name") or ""),
        SeatRankRow.long_party_name == str(row.get("long_party_name") or ""),
        SeatRankRow.short_party_name == str(row.get("short_party_name") or ""),
    ).limit(1)
    return db.scalar(stmt) is not None


def _seat_rank_from_preview(row: dict[str, Any]) -> SeatRankRow:
    return SeatRankRow(
        trade_date=str(row.get("trade_date") or ""),
        exchange=str(row.get("exchange") or ""),
        variety=str(row.get("variety") or ""),
        contract=str(row.get("contract") or ""),
        rank=row.get("rank"),
        vol_party_name=str(row.get("vol_party_name") or ""),
        vol=row.get("vol"),
        vol_chg=row.get("vol_chg"),
        long_party_name=str(row.get("long_party_name") or ""),
        long_open_interest=row.get("long_open_interest"),
        long_open_interest_chg=row.get("long_open_interest_chg"),
        short_party_name=str(row.get("short_party_name") or ""),
        short_open_interest=row.get("short_open_interest"),
        short_open_interest_chg=row.get("short_open_interest_chg"),
        raw_json=json.dumps({"promotion": True, "record_id": row.get("record_id"), "source_file_id": row.get("source_file_id"), "source": row.get("source"), "row": row}, ensure_ascii=False, default=str),
    )


def _update_gap_after_promotion(db: Session, source_file: SourceFile, inserted: int) -> None:
    if inserted <= 0:
        return
    gap = db.scalar(select(DataGap).where(
        DataGap.trade_date == source_file.trade_date,
        DataGap.exchange == source_file.exchange,
        DataGap.kind == "seat_rank",
    ))
    if not gap:
        gap = DataGap(trade_date=source_file.trade_date, exchange=source_file.exchange, kind="seat_rank")
        db.add(gap)
    gap.status = "resolved"
    gap.severity = "warning"
    gap.rows = inserted
    gap.message = f"resolved by parser promotion from raw archive #{source_file.id}"
    gap.resolved_at = datetime.utcnow()
