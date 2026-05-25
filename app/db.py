from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.replace("sqlite:///", "", 1)
    if not raw_path or raw_path == ":memory:":
        return
    parent = Path(raw_path).expanduser().parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Do not make importing app.db fail just because the configured SQLite
        # parent is read-only or mounted later by the runtime. The actual DB
        # connection will still surface a precise error if the file is unusable.
        pass


def _engine_url() -> str:
    url = get_settings().database.url
    _ensure_sqlite_parent(url)
    return url


_engine_url_value = _engine_url()
engine = create_engine(_engine_url_value, connect_args={"check_same_thread": False} if _engine_url_value.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    seed_contract_metadata()


def seed_contract_metadata() -> None:
    from app.metadata.variety_meta import EXCHANGE_NAME_TO_CODE, VARIETY_META_BY_SYMBOL
    from app.models import Contract
    from app.services.structure import sector_for

    db = SessionLocal()
    try:
        existing = {(r.exchange or "", (r.symbol or "").upper()): r for r in db.query(Contract).all()}
        changed = False
        for symbol, meta in VARIETY_META_BY_SYMBOL.items():
            name, _, exchange_name = meta
            exchange = EXCHANGE_NAME_TO_CODE.get(exchange_name, exchange_name)
            key = (exchange, symbol.upper())
            row = existing.get(key)
            if not row:
                row = Contract(symbol=symbol.upper(), exchange=exchange)
                db.add(row)
                existing[key] = row
                changed = True
            updates = {
                "name": name,
                "sector": sector_for(symbol),
                "active": True,
            }
            for attr, value in updates.items():
                if getattr(row, attr) != value:
                    setattr(row, attr, value)
                    changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
