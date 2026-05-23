from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import BasisDaily, DailyBar, DataGap, SeatRankRow, WarehouseReceiptDaily
from app.services.coverage_matrix import build_coverage_matrix


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        trade_date = "20260523"
        db.add(DailyBar(
            trade_date=trade_date,
            exchange="DCE",
            symbol="A",
            contract="A2607",
            close=4000,
            volume=100,
            open_interest=200,
        ))
        db.add(SeatRankRow(
            trade_date=trade_date,
            exchange="DCE",
            variety="A",
            rank=1,
            long_party_name="测试席位",
            long_open_interest=100,
            long_open_interest_chg=10,
        ))
        db.add(BasisDaily(trade_date=trade_date, symbol="A", basis=10, source="test"))
        db.add(WarehouseReceiptDaily(trade_date=trade_date, symbol="A", receipt_number=1, source="test"))
        db.commit()

        matrix = build_coverage_matrix(db, trade_date, sync_gaps=True)
        dce = next(row for row in matrix["rows"] if row["exchange"] == "DCE")
        cffex = next(row for row in matrix["rows"] if row["exchange"] == "CFFEX")
        czce = next(row for row in matrix["rows"] if row["exchange"] == "CZCE")

        assert dce["cells"]["daily"]["status"] == "ok"
        assert dce["cells"]["seat_rank"]["status"] == "ok"
        assert dce["cells"]["basis"]["status"] == "ok"
        assert dce["cells"]["warehouse_receipt"]["status"] == "ok"
        assert cffex["cells"]["basis"]["status"] == "not_supported"
        assert cffex["cells"]["warehouse_receipt"]["status"] == "not_supported"
        assert czce["cells"]["daily"]["status"] == "missing"

        gaps = db.scalars(select(DataGap).where(DataGap.trade_date == trade_date, DataGap.exchange == "CZCE", DataGap.kind == "daily")).all()
        assert len(gaps) == 1
        assert gaps[0].status == "open"
        assert gaps[0].severity == "error"

        # A later successful row should resolve an existing gap.
        db.add(DailyBar(trade_date=trade_date, exchange="CZCE", symbol="TA", contract="TA609", close=5000, volume=1, open_interest=1))
        db.commit()
        build_coverage_matrix(db, trade_date, sync_gaps=True)
        resolved = db.scalar(select(DataGap).where(DataGap.trade_date == trade_date, DataGap.exchange == "CZCE", DataGap.kind == "daily"))
        assert resolved.status == "resolved"
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
