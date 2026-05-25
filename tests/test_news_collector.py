from __future__ import annotations

import os

os.environ.setdefault("FUTURES_DAILY_DB", "tmp/test.db")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, _ensure_sqlite_parent
from app.models import MarketSnapshot
from app.services import news_collector


def check() -> None:
    _ensure_sqlite_parent("sqlite:////proc/forbidden/futures_daily.db")
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    original_sources = news_collector.NEWS_SOURCES
    original_fetchers = (
        news_collector.fetch_eastmoney_search,
        news_collector.fetch_sina_roll,
        news_collector.fetch_quhe_kuaixun,
        news_collector.fetch_article_links,
        news_collector.fetch_cls_depth,
    )
    try:
        news_collector.NEWS_SOURCES = []
        first = news_collector.collect_news_digest(db, "20260525")
        second = news_collector.collect_news_digest(db, "20260525")

        assert first["saved"] == 0
        assert second["saved"] == 0
        snapshots = db.query(MarketSnapshot).filter(
            MarketSnapshot.trade_date == "20260525",
            MarketSnapshot.exchange == "ALL",
            MarketSnapshot.source == news_collector.SOURCE,
            MarketSnapshot.snapshot_type == "news_digest",
        ).all()
        assert len(snapshots) == 1
        latest = news_collector.load_latest_news_digest(db, "20260525")
        assert latest["status"] == "ok"
        assert latest["items"] == []

        news_collector.fetch_eastmoney_search = lambda *args, **kwargs: [{"title": "A", "url": "u1"}]  # type: ignore[assignment]
        news_collector.fetch_sina_roll = lambda *args, **kwargs: [{"title": "B", "url": "u2"}]  # type: ignore[assignment]
        news_collector.fetch_quhe_kuaixun = lambda *args, **kwargs: []  # type: ignore[assignment]
        news_collector.fetch_article_links = lambda *args, **kwargs: []  # type: ignore[assignment]
        news_collector.fetch_cls_depth = lambda *args, **kwargs: []  # type: ignore[assignment]
        fetched = news_collector.fetch_source_items({"name": "x", "url": "y", "kind": "eastmoney_search", "queries": ["q"]})
        assert len(fetched) == 1
    finally:
        (
            news_collector.fetch_eastmoney_search,
            news_collector.fetch_sina_roll,
            news_collector.fetch_quhe_kuaixun,
            news_collector.fetch_article_links,
            news_collector.fetch_cls_depth,
        ) = original_fetchers
        news_collector.NEWS_SOURCES = original_sources
        db.close()



if __name__ == "__main__":
    check()
    print("ok")
