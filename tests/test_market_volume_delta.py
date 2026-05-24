from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.markets import _build_intraday_snapshot
from app.db import Base
from app.models import DailyBar


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(DailyBar(trade_date="20260522", exchange="SHFE", symbol="RU", contract="RU2609", close=100, pre_close=99, volume=100, open_interest=10))
        db.add(DailyBar(trade_date="20260523", exchange="SHFE", symbol="RU", contract="RU2609", close=102, pre_close=100, volume=160, open_interest=12))
        db.add(DailyBar(trade_date="20260523", exchange="DCE", symbol="A", contract="A2607", close=98, pre_close=100, volume=40, open_interest=8))
        db.commit()

        payload = _build_intraday_snapshot(db, "20260523")
        market = payload["market"]
        assert market["volume"] == 200
        assert market["volume_prev"] == 100
        assert market["volume_delta"] == 100
        assert market["volume_delta_pct"] == 100.0
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
