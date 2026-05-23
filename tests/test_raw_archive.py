from __future__ import annotations

import os
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.raw_archive import archive_fetch_result, archive_payload, list_archives, read_archive


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_raw_archive"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = archive_payload(
            db,
            trade_date="20260523",
            exchange="DCE",
            kind="daily",
            source="unit",
            payload={"rows": [{"contract": "A2607"}], "error": None},
        )
        assert row.rows == 1
        assert row.size_bytes > 0
        assert row.sha256
        assert "20260523" in row.path
        db.commit()

        rows = list_archives(db, trade_date="20260523", exchange="DCE", kind="daily")
        assert len(rows) == 1
        loaded = read_archive(rows[0])
        assert loaded["exists"] is True
        assert loaded["payload"]["rows"][0]["contract"] == "A2607"

        result = SimpleNamespace(rows=[{"x": 1}, {"x": 2}], error="partial", meta={"m": 1})
        row2 = archive_fetch_result(db, trade_date="20260523", exchange="CZCE", kind="seat_rank", source="unit", result=result)
        assert row2.rows == 2
        assert row2.error == "partial"
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
