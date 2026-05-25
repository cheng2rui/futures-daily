"""Regression test: ensure collector never deletes existing data when fetch returns nothing."""

from __future__ import annotations

import os

# Must be set BEFORE importing app modules
os.environ["FUTURES_DAILY_DB"] = "data/futures_daily.db"

from datetime import date
from unittest.mock import MagicMock, patch

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import (
    BasisDaily, CapitalFlowDaily, DailyBar,
    QuheContract, QuheHistoryHolding,
    SeatRankRow, WarehouseReceiptDaily,
)
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.quhe_collector import (
    SOURCE,
    collect_basis,
    collect_capital_flow,
    collect_quhe_history_holding,
    collect_warehouse_receipts,
)


def _make_result(rows=None, error=None):
    result = MagicMock()
    result.rows = rows or []
    result.error = error
    return result


def _make_quhe_result(rows=None, error=None, meta=None):
    result = MagicMock()
    result.rows = rows or []
    result.error = error
    result.meta = meta or {}
    return result


def check() -> None:
    db = SessionLocal()
    trade_date = date.today().strftime("%Y%m%d")

    # ── DailyBar protection ──────────────────────────────────────────────────
    db.execute(delete(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE"))
    db.add(DailyBar(trade_date=trade_date, exchange="SHFE", symbol="RB", contract="RB2509",
                    open=3700, high=3750, low=3690, close=3720,
                    pre_close=3710, volume=100000, open_interest=50000,
                    turnover=None, settlement=None, raw_json="{}"))
    db.commit()

    with patch("app.services.collector.get_market_provider") as mock_reg:
        mock_provider = MagicMock()
        mock_provider.fetch_daily.return_value = _make_result(rows=[], error="network timeout")
        mock_reg.return_value = mock_provider
        result = collect_daily_market(db, trade_date=trade_date, exchanges=["SHFE"])
        shfe_result = next(r for r in result["results"] if r["exchange"] == "SHFE")

    assert shfe_result["saved"] == 0, f"DailyBar: expected saved=0, got {shfe_result['saved']}"
    remaining = db.scalars(select(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE")).all()
    assert len(remaining) == 1, f"DailyBar: expected 1 row, got {len(remaining)}"

    # ── SeatRankRow protection ───────────────────────────────────────────────
    db.execute(delete(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE"))
    db.add(SeatRankRow(trade_date=trade_date, exchange="DCE", variety="M", contract="M2509",
                       rank=1, vol_party_name="永安", vol=5000, vol_chg=200,
                       long_party_name="", long_open_interest=None, long_open_interest_chg=None,
                       short_party_name="", short_open_interest=None, short_open_interest_chg=None,
                       raw_json="{}"))
    db.commit()

    with patch("app.services.collector.get_market_provider") as mock_reg:
        mock_provider = MagicMock()
        mock_provider.fetch_seat_rank.return_value = _make_result(rows=[], error="source unavailable")
        mock_reg.return_value = mock_provider
        result3 = collect_seat_ranks(db, trade_date=trade_date, exchanges=["DCE"])
        dce_result = next(r for r in result3["results"] if r["exchange"] == "DCE")

    assert dce_result["saved"] == 0
    existing_rank = db.scalars(select(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE")).all()
    assert len(existing_rank) == 1
    assert existing_rank[0].vol_party_name == "永安"

    # ── CapitalFlowDaily protection ─────────────────────────────────────────
    db.execute(delete(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date, CapitalFlowDaily.source == SOURCE))
    db.add(CapitalFlowDaily(trade_date=trade_date, symbol="RU", product_code="RU", product_name="天然橡胶",
                            amount=1000.0, source=SOURCE, raw_json="{}"))
    db.commit()
    with patch("app.services.quhe_collector.QuheSource") as MockQS:
        MockQS.return_value.fetch_capital_flow.return_value = _make_quhe_result(error="network timeout")
        r = collect_capital_flow(db, trade_date)
    assert r["saved"] == 0, f"capital_flow: expected saved=0, got {r['saved']}"
    remaining = db.scalars(select(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date, CapitalFlowDaily.symbol == "RU")).all()
    assert len(remaining) == 1, "capital_flow: existing row must survive failed fetch"

    # ── BasisDaily protection ────────────────────────────────────────────────
    db.execute(delete(BasisDaily).where(BasisDaily.trade_date == trade_date, BasisDaily.source == SOURCE))
    db.add(BasisDaily(trade_date=trade_date, symbol="M", product_code="M", product_name="豆粕",
                      spot_price=3000.0, main_contract_code="M2509", source=SOURCE, raw_json="{}"))
    db.commit()
    with patch("app.services.quhe_collector.QuheSource") as MockQS:
        MockQS.return_value.fetch_basis.return_value = _make_quhe_result(error="source unavailable")
        r = collect_basis(db, trade_date)
    assert r["saved"] == 0, f"basis: expected saved=0, got {r['saved']}"
    remaining = db.scalars(select(BasisDaily).where(BasisDaily.trade_date == trade_date, BasisDaily.symbol == "M")).all()
    assert len(remaining) == 1, "basis: existing row must survive failed fetch"

    # ── WarehouseReceiptDaily protection ─────────────────────────────────────
    db.execute(delete(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date, WarehouseReceiptDaily.source == SOURCE))
    db.add(WarehouseReceiptDaily(trade_date=trade_date, symbol="CU", product_code="CU", product_name="铜",
                                receipt_number=5000.0, source=SOURCE, raw_json="{}"))
    db.commit()
    with patch("app.services.quhe_collector.QuheSource") as MockQS:
        MockQS.return_value.fetch_warehouse_receipts.return_value = _make_quhe_result(error="source unavailable")
        r = collect_warehouse_receipts(db, trade_date)
    assert r["saved"] == 0, f"warehouse_receipts: expected saved=0, got {r['saved']}"
    remaining = db.scalars(select(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date, WarehouseReceiptDaily.symbol == "CU")).all()
    assert len(remaining) == 1, "warehouse_receipts: existing row must survive failed fetch"

    # ── QuheHistoryHolding protection ───────────────────────────────────────
    db.execute(delete(QuheContract))
    db.execute(delete(QuheHistoryHolding).where(QuheHistoryHolding.trade_date == trade_date, QuheHistoryHolding.source == SOURCE))
    db.add(QuheContract(product_code="RU", symbol="RU", product_name="天然橡胶", variety_code="RU",
                        variety_name="天然橡胶", board_name="SHFE_RU", is_main=True, raw_json="{}"))
    db.add(QuheHistoryHolding(trade_date=trade_date, symbol="RU", product_code="RU", product_name="天然橡胶",
                              symbol_code="RU", long_total=1000.0, source=SOURCE, raw_json="{}"))
    db.commit()
    contracts = db.scalars(select(QuheContract)).all()
    with patch("app.services.quhe_collector.QuheSource") as MockQS, \
         patch("app.services.quhe_collector.main_quhe_contracts", return_value=contracts):
        MockQS.return_value.fetch_history_holding.return_value = _make_quhe_result(error="network timeout")
        r = collect_quhe_history_holding(db, trade_date)
    assert r["saved"] == 0, f"history_holding: expected saved=0, got {r['saved']}"
    remaining = db.scalars(select(QuheHistoryHolding).where(QuheHistoryHolding.trade_date == trade_date, QuheHistoryHolding.symbol == "RU")).all()
    assert len(remaining) == 1, "history_holding: existing row must survive failed fetch"

    # Clean up
    db.execute(delete(DailyBar).where(DailyBar.trade_date == trade_date, DailyBar.exchange == "SHFE"))
    db.execute(delete(SeatRankRow).where(SeatRankRow.trade_date == trade_date, SeatRankRow.exchange == "DCE"))
    db.execute(delete(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date, CapitalFlowDaily.source == SOURCE))
    db.execute(delete(BasisDaily).where(BasisDaily.trade_date == trade_date, BasisDaily.source == SOURCE))
    db.execute(delete(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date, WarehouseReceiptDaily.source == SOURCE))
    db.execute(delete(QuheHistoryHolding).where(QuheHistoryHolding.trade_date == trade_date, QuheHistoryHolding.source == SOURCE))
    db.commit()
    db.close()


if __name__ == "__main__":
    check()
    print("ok")
