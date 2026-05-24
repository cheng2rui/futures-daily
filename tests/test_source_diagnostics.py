from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CrawlerRun, DailyBar, DataGap
from app.services.coverage_matrix import build_coverage_matrix
from app.services.source_diagnostics import diagnose_weak_sources


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        trade_date = "20260523"
        db.add(DailyBar(trade_date=trade_date, exchange="INE", symbol="SC", contract="SC2607", close=500, volume=1, open_interest=1))
        db.add(CrawlerRun(trade_date=trade_date, exchange="DCE", kind="seat_rank", source="akshare", status="failed", rows=0, saved=0, error="DCE seat rank fallback empty"))
        db.add(DataGap(trade_date=trade_date, exchange="DCE", kind="seat_rank", severity="error", status="open", message="DCE seat rank fallback empty"))
        db.commit()

        matrix = build_coverage_matrix(db, trade_date, sync_gaps=True)
        ine = next(row for row in matrix["rows"] if row["exchange"] == "INE")
        assert ine["cells"]["seat_rank"]["status"] == "not_supported"
        assert "公开 adapter" in ine["cells"]["seat_rank"]["message"]

        diag = diagnose_weak_sources(db, trade_date)
        dce = next(row for row in diag["exchanges"] if row["exchange"] == "DCE")
        ine_diag = next(row for row in diag["exchanges"] if row["exchange"] == "INE")
        seat_issue = next(issue for issue in dce["issues"] if issue["kind"] == "seat_rank")
        assert seat_issue["error_category"]["code"] == "empty"
        assert dce["error_summary"]["top_code"] == "empty"
        assert any(action["type"] == "external_source" for action in dce["actions"])
        assert any(issue["kind"] == "seat_rank" and issue["status"] == "not_supported" for issue in ine_diag["issues"])
        assert any(action["type"] == "adapter" for action in ine_diag["actions"])
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
