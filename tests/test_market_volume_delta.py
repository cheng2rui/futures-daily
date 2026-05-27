from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.markets import _build_intraday_snapshot, intraday_snapshot
from app.db import Base
from app.models import DailyBar
import app.api.markets as markets_api


def check() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(DailyBar(trade_date="20260522", exchange="SHFE", symbol="RU", contract="RU2609", close=100, pre_close=99, volume=100, open_interest=10))
        db.add(DailyBar(trade_date="20260523", exchange="SHFE", symbol="RU", contract="RU2609", close=102, pre_close=100, volume=160, open_interest=12))
        db.add(DailyBar(trade_date="20260523", exchange="DCE", symbol="A", contract="A2607", close=98, pre_close=100, volume=40, open_interest=8))
        db.add(DailyBar(trade_date="20260523", exchange="SHFE", symbol="CU", contract="CU2606", close=None, pre_close=50000, volume=300, open_interest=20))
        db.add(DailyBar(trade_date="20260523", exchange="SHFE", symbol="CU", contract="CU2607", close=None, pre_close=50100, volume=200, open_interest=18))
        db.commit()

        payload = _build_intraday_snapshot(db, "20260523")
        market = payload["market"]
        assert market["volume"] == 700
        assert market["volume_prev"] == 100
        assert market["volume_delta"] == 600
        assert market["volume_delta_pct"] == 600.0
        assert market["main_contracts"] == 3
        assert payload["rankings"]["volume"][0]["contract"] == "CU2606"
    finally:
        db.close()


def check_intraday_defaults_to_candidate_trade_date() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(DailyBar(trade_date="20260525", exchange="SHFE", symbol="RU", contract="RU2609", close=100, pre_close=99, volume=100, open_interest=10))
        db.commit()
        original = markets_api.latest_candidate_trade_date
        markets_api.latest_candidate_trade_date = lambda: "20260527"  # type: ignore[assignment]
        try:
            payload = intraday_snapshot(db=db)
        finally:
            markets_api.latest_candidate_trade_date = original  # type: ignore[assignment]

        assert payload["trade_date"] == "20260527"
        assert payload["market"]["contracts"] == 0
    finally:
        db.close()


if __name__ == "__main__":
    check()
    check_intraday_defaults_to_candidate_trade_date()
    print("ok")
