from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CrawlerRun, DailyBar, DataGap, MarketSnapshot, SeatRankRow
from app.services.normalizer import normalize_daily_row, normalize_seat_row
from app.services.raw_archive import archive_fetch_result
from app.sources.registry import get_market_provider


def _enabled_exchanges(exchanges: list[str] | tuple[str, ...] | None = None) -> list[str]:
    enabled = [str(x).upper() for x in get_settings().exchanges.enabled]
    if not exchanges:
        return enabled
    requested = [str(x).upper() for x in exchanges]
    return [x for x in requested if x in enabled]


def collect_daily_market(db: Session, trade_date: str | None = None, exchanges: list[str] | tuple[str, ...] | None = None) -> dict:
    trade_date = trade_date or date.today().strftime("%Y%m%d")
    source = get_market_provider("akshare")
    results = []
    for exchange in _enabled_exchanges(exchanges):
        run = start_crawler_run(db, trade_date, exchange, "daily")
        db.execute(delete(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == exchange))
        result = source.fetch_daily(trade_date, exchange)
        archive_fetch_result(db, trade_date=trade_date, exchange=exchange, kind="daily", source="akshare", result=result)
        db.add(MarketSnapshot(
            trade_date=trade_date,
            exchange=exchange,
            source="akshare",
            snapshot_type="daily",
            raw_json=json.dumps({"rows": result.rows, "error": result.error}, ensure_ascii=False, default=str),
        ))
        saved = 0
        for row in result.rows:
            n = normalize_daily_row(exchange, row)
            if not n["contract"]:
                continue
            db.add(DailyBar(
                trade_date=trade_date,
                exchange=exchange,
                symbol=n["symbol"],
                contract=n["contract"],
                open=n["open"], high=n["high"], low=n["low"], close=n["close"],
                pre_close=n["pre_close"], volume=n["volume"], open_interest=n["open_interest"],
                turnover=n["turnover"], settlement=n["settlement"],
                raw_json=json.dumps(n["raw"], ensure_ascii=False, default=str),
            ))
            saved += 1
        finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
        update_data_gap(db, trade_date, exchange, "daily", rows=saved, error=result.error)
        results.append({"exchange": exchange, "rows": len(result.rows), "saved": saved, "error": result.error})
    db.commit()
    return {"trade_date": trade_date, "results": results}


def collect_seat_ranks(db: Session, trade_date: str | None = None, exchanges: list[str] | tuple[str, ...] | None = None) -> dict:
    trade_date = trade_date or date.today().strftime("%Y%m%d")
    source = get_market_provider("akshare")
    results = []
    for exchange in _enabled_exchanges(exchanges):
        run = start_crawler_run(db, trade_date, exchange, "seat_rank")
        db.execute(delete(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == exchange))
        result = source.fetch_seat_rank(trade_date, exchange)
        archive_fetch_result(db, trade_date=trade_date, exchange=exchange, kind="seat_rank", source="akshare", result=result)
        db.add(MarketSnapshot(
            trade_date=trade_date,
            exchange=exchange,
            source="akshare",
            snapshot_type="seat_rank",
            raw_json=json.dumps({"rows": result.rows[:2000], "row_count": len(result.rows), "error": result.error}, ensure_ascii=False, default=str),
        ))
        saved = 0
        for row in result.rows:
            n = normalize_seat_row(exchange, row)
            db.add(SeatRankRow(
                trade_date=trade_date,
                exchange=exchange,
                variety=n["variety"],
                contract=n["contract"],
                rank=n["rank"],
                vol_party_name=n["vol_party_name"], vol=n["vol"], vol_chg=n["vol_chg"],
                long_party_name=n["long_party_name"], long_open_interest=n["long_open_interest"], long_open_interest_chg=n["long_open_interest_chg"],
                short_party_name=n["short_party_name"], short_open_interest=n["short_open_interest"], short_open_interest_chg=n["short_open_interest_chg"],
                raw_json=json.dumps(n["raw"], ensure_ascii=False, default=str),
            ))
            saved += 1
        finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
        update_data_gap(db, trade_date, exchange, "seat_rank", rows=saved, error=result.error)
        results.append({"exchange": exchange, "rows": len(result.rows), "saved": saved, "error": result.error})
    db.commit()
    return {"trade_date": trade_date, "results": results}


def start_crawler_run(db: Session, trade_date: str, exchange: str, kind: str, source: str = "akshare") -> CrawlerRun:
    run = CrawlerRun(trade_date=trade_date, exchange=exchange, kind=kind, source=source, status="running", started_at=datetime.utcnow())
    db.add(run)
    db.flush()
    return run


def finish_crawler_run(run: CrawlerRun, rows: int, saved: int, error: str | None) -> None:
    run.rows = rows
    run.saved = saved
    run.error = error or ""
    run.status = "success" if saved > 0 and not error else "partial" if saved > 0 else "failed"
    run.finished_at = datetime.utcnow()


def update_data_gap(db: Session, trade_date: str, exchange: str, kind: str, rows: int, error: str | None) -> None:
    gap = db.scalar(select(DataGap).where(DataGap.trade_date == trade_date, DataGap.exchange == exchange, DataGap.kind == kind))
    if rows > 0 and not error:
        if gap:
            gap.status = "resolved"
            gap.rows = rows
            gap.message = "resolved by latest collection"
            gap.resolved_at = datetime.utcnow()
        return
    if not gap:
        gap = DataGap(trade_date=trade_date, exchange=exchange, kind=kind)
        db.add(gap)
    gap.status = "open"
    gap.severity = "error" if rows == 0 else "warning"
    gap.rows = rows
    gap.message = error or "empty result"
    gap.resolved_at = None
