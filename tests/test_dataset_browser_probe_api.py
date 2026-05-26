from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.api.dataset import run_browser_probe
from app.models import SourceFile
from app.services.raw_replay import replay_source_file


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_dataset_browser_probe"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = run_browser_probe("20260526", "DCE", kind="seat_rank", url="data:text/html,<title>DCE API</title><table><tr><td>持仓排名</td></tr></table>", db=db)
        assert result["ok"] is True
        row = db.scalar(select(SourceFile).where(SourceFile.id == result["archive_id"]))
        assert row is not None
        assert row.kind == "seat_rank_browser_probe"
        replay = replay_source_file(db, row.id)
        assert replay["status"] == "ok"
        assert replay["stats"]["contains_table"] is True
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
