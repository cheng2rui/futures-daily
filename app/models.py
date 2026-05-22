from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(64), default="akshare")
    snapshot_type: Mapped[str] = mapped_column(String(64), index=True)
    raw_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    sector: Mapped[str] = mapped_column(String(64), default="未分类")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_contract_symbol_exchange"),)


class DailyBar(Base):
    __tablename__ = "daily_bars"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    contract: Mapped[str] = mapped_column(String(32), index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    settlement: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    __table_args__ = (UniqueConstraint("trade_date", "exchange", "contract", name="uq_daily_bar"),)


class SeatRankRow(Base):
    __tablename__ = "seat_rank_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    variety: Mapped[str] = mapped_column(String(32), index=True)
    contract: Mapped[str] = mapped_column(String(32), default="", index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vol_party_name: Mapped[str] = mapped_column(String(128), default="")
    vol: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_chg: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_party_name: Mapped[str] = mapped_column(String(128), default="")
    long_open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_open_interest_chg: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_party_name: Mapped[str] = mapped_column(String(128), default="")
    short_open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_open_interest_chg: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")


class WatchSymbol(Base):
    __tablename__ = "watch_symbols"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    sector: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    trade_date: Mapped[str] = mapped_column(String(10), default="", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")


class CrawlerRun(Base):
    __tablename__ = "crawler_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="akshare")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    saved: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataGap(Base):
    __tablename__ = "data_gaps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("trade_date", "exchange", "kind", name="uq_data_gap_day_exchange_kind"),)


class VarietyDailyFact(Base):
    __tablename__ = "variety_daily_facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    sector: Mapped[str] = mapped_column(String(64), default="")
    contracts: Mapped[int] = mapped_column(Integer, default=0)
    main_contract: Mapped[str] = mapped_column(String(32), default="")
    main_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    notional_oi: Mapped[float | None] = mapped_column(Float, nullable=True)
    seat_rank_rows: Mapped[int] = mapped_column(Integer, default=0)
    seat_net_delta_top20: Mapped[float | None] = mapped_column(Float, nullable=True)
    archive_net_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    archive_long_short_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    archive_long_cr5: Mapped[float | None] = mapped_column(Float, nullable=True)
    archive_short_cr5: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_daily: Mapped[str] = mapped_column(String(32), default="missing")
    quality_seat_rank: Mapped[str] = mapped_column(String(32), default="missing")
    quality_archive_signal: Mapped[str] = mapped_column(String(32), default="missing")
    fact_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "exchange", "symbol", name="uq_variety_daily_fact"),)


class DailyCoverage(Base):
    __tablename__ = "daily_coverage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    varieties: Mapped[int] = mapped_column(Integer, default=0)
    with_seat_rank: Mapped[int] = mapped_column(Integer, default=0)
    with_archive_signal: Mapped[int] = mapped_column(Integer, default=0)
    daily_status: Mapped[str] = mapped_column(String(32), default="missing")
    seat_status: Mapped[str] = mapped_column(String(32), default="missing")
    archive_status: Mapped[str] = mapped_column(String(32), default="missing")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "exchange", name="uq_daily_coverage"),)


class CapitalFlowDaily(Base):
    __tablename__ = "capital_flow_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    product_code: Mapped[str] = mapped_column(String(32), default="")
    product_name: Mapped[str] = mapped_column(String(128), default="")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="quheqihuo")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "symbol", "source", name="uq_capital_flow_daily"),)


class BasisDaily(Base):
    __tablename__ = "basis_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    product_code: Mapped[str] = mapped_column(String(32), default="")
    product_name: Mapped[str] = mapped_column(String(128), default="")
    exchange_name: Mapped[str] = mapped_column(String(128), default="")
    spot_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_contract_code: Mapped[str] = mapped_column(String(32), default="")
    main_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    highest: Mapped[float | None] = mapped_column(Float, nullable=True)
    lowest: Mapped[float | None] = mapped_column(Float, nullable=True)
    average: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="quheqihuo")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "symbol", "source", name="uq_basis_daily"),)


class WarehouseReceiptDaily(Base):
    __tablename__ = "warehouse_receipt_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    product_code: Mapped[str] = mapped_column(String(32), default="")
    product_name: Mapped[str] = mapped_column(String(128), default="")
    receipt_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    increase_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    increase_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    hand_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="quheqihuo")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "symbol", "source", name="uq_warehouse_receipt_daily"),)


class QuheHistoryHolding(Base):
    __tablename__ = "quhe_history_holding"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    product_code: Mapped[str] = mapped_column(String(32), default="")
    product_name: Mapped[str] = mapped_column(String(128), default="")
    exchange: Mapped[str] = mapped_column(String(16), default="", index=True)
    symbol_code: Mapped[str] = mapped_column(String(64), index=True)
    symbol_name: Mapped[str] = mapped_column(String(128), default="")
    long_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="quheqihuo")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("trade_date", "symbol", "symbol_code", "source", name="uq_quhe_history_holding"),)


class QuheContract(Base):
    __tablename__ = "quhe_contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    product_name: Mapped[str] = mapped_column(String(128), default="")
    board_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    board_name: Mapped[str] = mapped_column(String(128), default="")
    variety_code: Mapped[str] = mapped_column(String(64), index=True)
    variety_name: Mapped[str] = mapped_column(String(128), default="")
    quota_code: Mapped[str] = mapped_column(String(64), default="")
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("product_code", "variety_code", name="uq_quhe_contract_product_variety"),)


class SeatWatchlist(Base):
    __tablename__ = "seat_watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seat_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    alias: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
