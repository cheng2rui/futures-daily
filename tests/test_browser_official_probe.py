from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.browser.official_probe import probe_official_page


def check() -> None:
    os.environ["FUTURES_DAILY_RAW_ARCHIVE"] = "tmp/test_browser_probe"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = probe_official_page(db, trade_date="20260526", exchange="DCE", url="data:text/html,<title>DCE Probe</title><h1>ok</h1>")
        assert result["ok"] is True
        assert result["archive_id"] >= 1
        assert "DCE Probe" in result["title"]
        missing = probe_official_page(db, trade_date="20260526", exchange="XXX", url="")
        assert missing["ok"] is False
        assert missing["archive_id"] >= 1
    finally:
        db.close()


if __name__ == "__main__":
    check()
    print("ok")
