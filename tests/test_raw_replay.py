from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.raw_archive import archive_payload
from app.services.raw_replay import replay_source_file


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_raw_replay"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        daily = archive_payload(
            db,
            trade_date="20260523",
            exchange="DCE",
            kind="daily",
            source="unit",
            payload={"rows": [{"contract": "a2607", "close": "4012", "volume": "100"}, {"bad": "row"}]},
        )
        seat = archive_payload(
            db,
            trade_date="20260523",
            exchange="SHFE",
            kind="seat_rank",
            source="unit",
            payload={"rows": [{"symbol": "RU2609", "rank": "1", "long_party_name": "永安期货", "long_open_interest": "10"}]},
        )
        unsupported = archive_payload(
            db,
            trade_date="20260523",
            exchange="ALL",
            kind="basis",
            source="unit",
            payload={"rows": [{"x": 1}]},
        )
        db.commit()

        daily_result = replay_source_file(db, daily.id)
        assert daily_result["status"] == "partial"
        assert daily_result["input_rows"] == 2
        assert daily_result["parsed_rows"] == 1
        assert daily_result["sample"][0]["symbol"] == "A"
        assert daily_result["stats"]["contracts"] == 1

        seat_result = replay_source_file(db, seat.id)
        assert seat_result["status"] == "ok"
        assert seat_result["parsed_rows"] == 1
        assert seat_result["sample"][0]["variety"] == "RU"

        unsupported_result = replay_source_file(db, unsupported.id)
        assert unsupported_result["status"] == "unsupported"
        assert unsupported_result["input_rows"] == 1
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
