from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.metadata.variety_meta import EXCHANGE_NAME_TO_CODE, get_variety_name
from app.models import BasisDaily, CapitalFlowDaily, CrawlerRun, MarketSnapshot, QuheContract, QuheHistoryHolding, SeatRankRow, VarietyDailyFact, WarehouseReceiptDaily
from app.services.collector import finish_crawler_run, start_crawler_run, update_data_gap
from app.services.raw_archive import archive_fetch_result, archive_payload
from app.sources.quhe_source import QuheSource, dash_to_date8, date8_to_dash, ms_to_datetime

SOURCE = "quheqihuo"


def collect_quhe_enhancements(db: Session, trade_date: str) -> dict[str, Any]:
    source = QuheSource()
    results = {
        "capital_flow": collect_capital_flow(db, trade_date, source),
        "basis": collect_basis(db, trade_date, source),
        "basis_100ppi": collect_100ppi_basis(db, trade_date),
        "warehouse_receipt": collect_warehouse_receipts(db, trade_date, source),
        "warehouse_receipt_official": collect_official_warehouse_receipts(db, trade_date),
        "contract_tree": collect_contract_tree(db, trade_date, source),
        "history_holding": collect_quhe_history_holding(db, trade_date, source),
        "seat_rank_fallback": collect_quhe_seat_rank_fallback(db, trade_date, source),
    }
    db.commit()
    return {"trade_date": trade_date, "source": SOURCE, "results": results}


def collect_capital_flow(db: Session, trade_date: str, source: QuheSource | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    run = start_crawler_run(db, trade_date, "ALL", "capital_flow", source=SOURCE)
    result = source.fetch_capital_flow()
    archive_fetch_result(db, trade_date=trade_date, exchange="ALL", kind="capital_flow", source=SOURCE, result=result)
    db.add(MarketSnapshot(trade_date=trade_date, exchange="ALL", source=SOURCE, snapshot_type="capital_flow", raw_json=snapshot_json(result)))
    normalized = []
    src_time = ms_to_datetime((result.meta or {}).get("time"))
    for row in result.rows:
        symbol = normalize_symbol(row.get("productCode"))
        if not symbol:
            continue
        normalized.append({
            "symbol": symbol,
            "product_code": str(row.get("productCode") or ""),
            "product_name": str(row.get("productName") or ""),
            "amount": safe_float(row.get("price")),
            "src_time": src_time,
            "raw": row,
        })
    saved = len(normalized)
    if saved > 0:
        db.execute(delete(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date, CapitalFlowDaily.source == SOURCE))
        for n in normalized:
            db.add(CapitalFlowDaily(
                trade_date=trade_date,
                symbol=n["symbol"],
                product_code=n["product_code"],
                product_name=n["product_name"],
                amount=n["amount"],
                source_time=n["src_time"],
                source=SOURCE,
                raw_json=json.dumps(n["raw"], ensure_ascii=False, default=str),
                updated_at=datetime.utcnow(),
            ))
    finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
    update_data_gap(db, trade_date, "ALL", "capital_flow", saved, result.error)
    return {"rows": len(result.rows), "saved": saved, "error": result.error}


def collect_basis(db: Session, trade_date: str, source: QuheSource | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    run = start_crawler_run(db, trade_date, "ALL", "basis", source=SOURCE)
    result = source.fetch_basis()
    archive_fetch_result(db, trade_date=trade_date, exchange="ALL", kind="basis", source=SOURCE, result=result)
    db.add(MarketSnapshot(trade_date=trade_date, exchange="ALL", source=SOURCE, snapshot_type="basis", raw_json=snapshot_json(result)))
    normalized = []
    for row in result.rows:
        row_date = dash_to_date8(row.get("publishTime")) or trade_date
        if row_date != trade_date:
            continue
        symbol = normalize_symbol(row.get("productCode"))
        if not symbol:
            continue
        normalized.append({
            "symbol": symbol,
            "product_code": str(row.get("productCode") or ""),
            "product_name": str(row.get("name") or ""),
            "exchange_name": str(row.get("exchange") or ""),
            "spot_price": safe_float(row.get("price")),
            "main_contract_code": str(row.get("code") or ""),
            "main_price": safe_float(row.get("mainPrice")),
            "basis": safe_float(row.get("basis")),
            "basis_rate": safe_float(row.get("basisRate")),
            "highest": safe_float(row.get("highest")),
            "lowest": safe_float(row.get("lowest")),
            "average": safe_float(row.get("average")),
            "raw": row,
        })
    saved = len(normalized)
    if saved > 0:
        db.execute(delete(BasisDaily).where(BasisDaily.trade_date == trade_date, BasisDaily.source == SOURCE))
        for n in normalized:
            db.add(BasisDaily(
                trade_date=trade_date,
                symbol=n["symbol"],
                product_code=n["product_code"],
                product_name=n["product_name"],
                exchange_name=n["exchange_name"],
                spot_price=n["spot_price"],
                main_contract_code=n["main_contract_code"],
                main_price=n["main_price"],
                basis=n["basis"],
                basis_rate=n["basis_rate"],
                highest=n["highest"],
                lowest=n["lowest"],
                average=n["average"],
                source=SOURCE,
                raw_json=json.dumps(n["raw"], ensure_ascii=False, default=str),
                updated_at=datetime.utcnow(),
            ))
    finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
    update_data_gap(db, trade_date, "ALL", "basis", saved, result.error)
    return {"rows": len(result.rows), "saved": saved, "error": result.error}


def collect_100ppi_basis(db: Session, trade_date: str) -> dict[str, Any]:
    """Collect 100ppi spot/basis rows via AkShare as a fallback to Quhe basis.

    This source has sparse but useful coverage for some newer varieties that
    Quhe's basis list currently omits (e.g. PL/FU on 20260521). It is fallback
    only; data mart prefers Quhe rows when both sources exist.
    """
    import akshare as ak

    source = "akshare_100ppi"
    run = start_crawler_run(db, trade_date, "ALL", "basis_100ppi", source=source)
    facts = db.scalars(select(VarietyDailyFact).where(VarietyDailyFact.trade_date == trade_date)).all()
    vars_list = sorted({f.symbol.upper() for f in facts})
    try:
        df = ak.futures_spot_price(date=trade_date, vars_list=vars_list)
        rows = [] if df is None or df.empty else df.where(df.notnull(), None).to_dict(orient="records")
        saved = 0
        for row in rows:
            symbol = normalize_symbol(row.get("symbol"))
            if not symbol:
                continue
            existing = db.scalar(select(BasisDaily).where(
                BasisDaily.trade_date == trade_date,
                BasisDaily.symbol == symbol,
                BasisDaily.source == source,
            ))
            if not existing:
                existing = BasisDaily(trade_date=trade_date, symbol=symbol, source=source)
                db.add(existing)
            existing.product_code = symbol
            existing.product_name = get_variety_name(symbol)
            existing.exchange_name = ""
            existing.spot_price = safe_float(row.get("spot_price"))
            existing.main_contract_code = str(row.get("dominant_contract") or "")
            existing.main_price = safe_float(row.get("dominant_contract_price"))
            existing.basis = safe_float(row.get("dom_basis"))
            # AkShare returns basis rate as a ratio; Quhe uses percentage points.
            rate = safe_float(row.get("dom_basis_rate"))
            existing.basis_rate = round(rate * 100, 4) if rate is not None else None
            existing.highest = None
            existing.lowest = None
            existing.average = None
            existing.raw_json = json.dumps(row, ensure_ascii=False, default=str)
            existing.updated_at = datetime.utcnow()
            saved += 1
        finish_crawler_run(run, rows=len(rows), saved=saved, error=None if saved else "empty 100ppi basis rows")
        update_data_gap(db, trade_date, "ALL", "basis_100ppi", saved, None if saved else "empty 100ppi basis rows")
        return {"source": source, "rows": len(rows), "saved": saved, "error": None if saved else "empty 100ppi basis rows"}
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        finish_crawler_run(run, rows=0, saved=0, error=error)
        update_data_gap(db, trade_date, "ALL", "basis_100ppi", 0, error)
        return {"source": source, "rows": 0, "saved": 0, "error": error}


def collect_warehouse_receipts(db: Session, trade_date: str, source: QuheSource | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    run = start_crawler_run(db, trade_date, "ALL", "warehouse_receipt", source=SOURCE)
    result = source.fetch_warehouse_receipts()
    archive_fetch_result(db, trade_date=trade_date, exchange="ALL", kind="warehouse_receipt", source=SOURCE, result=result)
    db.add(MarketSnapshot(trade_date=trade_date, exchange="ALL", source=SOURCE, snapshot_type="warehouse_receipt", raw_json=snapshot_json(result)))
    normalized = []
    for row in result.rows:
        row_date = dash_to_date8(row.get("day")) or trade_date
        if row_date != trade_date:
            continue
        symbol = normalize_symbol(row.get("type"))
        if not symbol:
            continue
        normalized.append({
            "symbol": symbol,
            "product_code": str(row.get("type") or ""),
            "product_name": str(row.get("productName") or ""),
            "receipt_number": safe_float(row.get("receiptNumber")),
            "increase_number": safe_float(row.get("increaseNumber")),
            "increase_ratio": safe_float(row.get("increaseRatio")),
            "hand_number": safe_float(row.get("handNumber")),
            "raw": row,
        })
    saved = len(normalized)
    if saved > 0:
        db.execute(delete(WarehouseReceiptDaily).where(WarehouseReceiptDaily.trade_date == trade_date, WarehouseReceiptDaily.source == SOURCE))
        for n in normalized:
            db.add(WarehouseReceiptDaily(
                trade_date=trade_date,
                symbol=n["symbol"],
                product_code=n["product_code"],
                product_name=n["product_name"],
                receipt_number=n["receipt_number"],
                increase_number=n["increase_number"],
                increase_ratio=n["increase_ratio"],
                hand_number=n["hand_number"],
                source=SOURCE,
                raw_json=json.dumps(n["raw"], ensure_ascii=False, default=str),
                updated_at=datetime.utcnow(),
            ))
    finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
    update_data_gap(db, trade_date, "ALL", "warehouse_receipt", saved, result.error)
    return {"rows": len(result.rows), "saved": saved, "error": result.error}


def collect_official_warehouse_receipts(db: Session, trade_date: str) -> dict[str, Any]:
    """Collect official exchange warehouse receipt rows as a supplement to Quhe.

    Quhe's all-market daily endpoint is convenient but not complete for newer
    varieties (e.g. CZCE PL). Official AkShare adapters are uneven, so this
    collector saves what works and records per-exchange errors without replacing
    Quhe rows.
    """
    import akshare as ak

    source = "akshare_official"
    results: dict[str, Any] = {}
    total_saved = 0

    def save_row(symbol: str, product_name: str, receipt: Any, increase: Any, raw: dict[str, Any]) -> None:
        nonlocal total_saved
        symbol = normalize_symbol(symbol)
        if not symbol:
            return
        existing = db.scalar(select(WarehouseReceiptDaily).where(
            WarehouseReceiptDaily.trade_date == trade_date,
            WarehouseReceiptDaily.symbol == symbol,
            WarehouseReceiptDaily.source == source,
        ))
        if not existing:
            existing = WarehouseReceiptDaily(trade_date=trade_date, symbol=symbol, source=source)
            db.add(existing)
        existing.product_code = symbol
        existing.product_name = product_name or symbol
        existing.receipt_number = safe_float(receipt)
        existing.increase_number = safe_float(increase)
        existing.increase_ratio = None
        existing.hand_number = safe_float(receipt)
        existing.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        existing.updated_at = datetime.utcnow()
        total_saved += 1

    adapters = {
        "CZCE": lambda: ak.futures_warehouse_receipt_czce(date=trade_date),
        "GFEX": lambda: ak.futures_gfex_warehouse_receipt(date=trade_date),
        "SHFE": lambda: ak.futures_shfe_warehouse_receipt(date=trade_date),
        "DCE": lambda: ak.futures_warehouse_receipt_dce(date=trade_date),
    }
    for exchange, fetch in adapters.items():
        run = start_crawler_run(db, trade_date, exchange, "warehouse_receipt_official", source=source)
        saved_before = total_saved
        try:
            data = fetch()
            archive_payload(db, trade_date=trade_date, exchange=exchange, kind="warehouse_receipt_official", source=source, payload={"exchange": exchange, "rows": dataframe_dict(data)}, rows=len(data) if isinstance(data, dict) else 0)
            if not isinstance(data, dict):
                raise ValueError(f"unexpected data type: {type(data).__name__}")
            for raw_symbol, df in data.items():
                symbol = normalize_symbol(raw_symbol)
                if symbol == "PTA":
                    symbol = "TA"
                if df is None or getattr(df, "empty", True):
                    continue
                rows = df.where(df.notnull(), None).to_dict(orient="records")
                if exchange == "GFEX":
                    receipt = sum(safe_float(r.get("今日仓单量")) or 0 for r in rows)
                    increase = sum(safe_float(r.get("增减")) or 0 for r in rows)
                    product_name = str(rows[0].get("品种") or symbol) if rows else symbol
                    save_row(symbol, product_name, receipt, increase, {"exchange": exchange, "rows": rows})
                    continue
                total = next((r for r in rows if str(r.get("仓库编号") or r.get("仓库简称") or "").strip() == "总计"), None)
                if not total:
                    continue
                save_row(symbol, symbol, total.get("仓单数量"), total.get("当日增减"), {"exchange": exchange, "rows": rows})
            saved = total_saved - saved_before
            finish_crawler_run(run, rows=len(data), saved=saved, error=None if saved else "empty official warehouse rows")
            update_data_gap(db, trade_date, exchange, "warehouse_receipt_official", saved, None if saved else "empty official warehouse rows")
            results[exchange] = {"rows": len(data), "saved": saved, "error": None if saved else "empty official warehouse rows"}
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            finish_crawler_run(run, rows=0, saved=0, error=error)
            update_data_gap(db, trade_date, exchange, "warehouse_receipt_official", 0, error)
            results[exchange] = {"rows": 0, "saved": 0, "error": error}
    return {"source": source, "saved": total_saved, "exchanges": results}


def collect_contract_tree(db: Session, trade_date: str, source: QuheSource | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    run = start_crawler_run(db, trade_date, "ALL", "quhe_contract_tree", source=SOURCE)
    result = source.fetch_contract_tree()
    archive_fetch_result(db, trade_date=trade_date, exchange="ALL", kind="quhe_contract_tree", source=SOURCE, result=result)
    db.add(MarketSnapshot(trade_date=trade_date, exchange="ALL", source=SOURCE, snapshot_type="quhe_contract_tree", raw_json=snapshot_json(result)))
    saved = 0
    for product in result.rows:
        product_code = str(product.get("productCode") or "")
        product_name = str(product.get("productName") or "")
        symbol = normalize_symbol(product_code)
        for item in product.get("symbolList") or []:
            variety_code = str(item.get("varietyCode") or "")
            if not product_code or not variety_code:
                continue
            contract = db.scalar(select(QuheContract).where(QuheContract.product_code == product_code, QuheContract.variety_code == variety_code))
            if not contract:
                contract = QuheContract(product_code=product_code, variety_code=variety_code)
                db.add(contract)
            contract.symbol = symbol
            contract.product_name = product_name
            contract.board_id = item.get("boardId")
            contract.board_name = str(item.get("boardName") or "")
            contract.variety_name = str(item.get("varietyName") or "")
            contract.quota_code = str(item.get("quotaCode") or "")
            contract.is_main = bool(item.get("isMain") == 1)
            contract.raw_json = json.dumps(item, ensure_ascii=False, default=str)
            contract.updated_at = datetime.utcnow()
            saved += 1
    finish_crawler_run(run, rows=len(result.rows), saved=saved, error=result.error)
    update_data_gap(db, trade_date, "ALL", "quhe_contract_tree", saved, result.error)
    return {"rows": len(result.rows), "saved": saved, "error": result.error}


def collect_quhe_history_holding(db: Session, trade_date: str, source: QuheSource | None = None, exchanges: set[str] | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    # Commodity exchanges have the best coverage; CFFEX/EC are mostly empty in probes.
    exchanges = exchanges or {"DCE", "CZCE", "SHFE", "GFEX", "INE"}
    run = start_crawler_run(db, trade_date, "ALL", "quhe_history_holding", source=SOURCE)
    contracts = [c for c in main_quhe_contracts(db, None) if BOARD_TO_EXCHANGE.get(c.board_name) in exchanges]
    all_rows: list[tuple[QuheContract, dict[str, Any]]] = []
    fetched = 0
    errors: list[str] = []
    failed_contracts: list[tuple[QuheContract, str]] = []
    for contract in contracts:
        time.sleep(0.08)
        result = source.fetch_history_holding(contract.variety_code, limit=20)
        if result.error:
            failed_contracts.append((contract, result.error))
            continue
        for row in result.rows:
            all_rows.append((contract, row))
        fetched += len(result.rows)

    for contract, first_error in failed_contracts:
        time.sleep(0.8)
        result = source.fetch_history_holding(contract.variety_code, limit=20)
        if result.error:
            errors.append(f"{contract.variety_code}: {result.error or first_error}")
            continue
        for row in result.rows:
            all_rows.append((contract, row))
        fetched += len(result.rows)

    saved = 0
    if all_rows:
        db.execute(delete(QuheHistoryHolding).where(QuheHistoryHolding.trade_date == trade_date, QuheHistoryHolding.source == SOURCE))
        for contract, row in all_rows:
            saved += _save_history_row(db, trade_date, contract, row)
    error_text = "; ".join(errors[:8]) if errors else None
    finish_crawler_run(run, rows=fetched, saved=saved, error=error_text)
    update_data_gap(db, trade_date, "ALL", "quhe_history_holding", saved, error_text)
    return {"contracts": len(contracts), "rows": fetched, "saved": saved, "error": error_text}


def _save_history_row(db: Session, trade_date: str, contract: QuheContract, row: dict[str, Any]) -> int:
    exchange = BOARD_TO_EXCHANGE.get(contract.board_name, "")
    row_date = date8_from_ms(row.get("date"))
    if row_date != trade_date:
        return 0
    long_total = safe_float(row.get("manyTo"))
    short_total = safe_float(row.get("emptyTo"))
    db.add(QuheHistoryHolding(
        trade_date=trade_date,
        symbol=normalize_symbol(contract.product_code),
        product_code=contract.product_code,
        product_name=contract.product_name,
        exchange=exchange,
        symbol_code=contract.variety_code,
        symbol_name=contract.variety_name,
        long_total=long_total,
        short_total=short_total,
        net_total=(long_total or 0) - (short_total or 0),
        source=SOURCE,
        raw_json=json.dumps(row, ensure_ascii=False, default=str),
        updated_at=datetime.utcnow(),
    ))
    return 1


BOARD_TO_EXCHANGE = {
    "上海期货交易所": "SHFE",
    "大连商品交易所": "DCE",
    "郑州商品交易所": "CZCE",
    "中国金融期货交易所": "CFFEX",
    "上海国际能源交易中心": "INE",
    "上期能源": "INE",
    "广州期货交易所": "GFEX",
}


def collect_quhe_seat_rank_fallback(db: Session, trade_date: str, source: QuheSource | None = None, exchanges: set[str] | None = None) -> dict[str, Any]:
    source = source or QuheSource()
    # Commodity exchanges only. CFFEX probes are mostly empty; official/AkShare coverage is better there.
    exchanges = exchanges or {"DCE", "CZCE", "SHFE", "GFEX", "INE"}
    trade_date_dash = date8_to_dash(trade_date)
    total_saved = 0
    total_rows = 0
    errors: list[str] = []
    per_exchange: dict[str, dict[str, Any]] = {}
    for exchange in sorted(exchanges):
        run = start_crawler_run(db, trade_date, exchange, "seat_rank_fallback", source=SOURCE)
        contracts = main_quhe_contracts(db, exchange)
        saved = 0
        fetched = 0
        skipped = 0
        attempted = 0
        exchange_errors: list[str] = []
        for contract in contracts:
            variety = normalize_symbol(contract.product_code)
            existing = db.query(SeatRankRow).filter(
                SeatRankRow.trade_date == trade_date,
                SeatRankRow.exchange == exchange,
                SeatRankRow.variety == variety,
            ).count()
            if existing > 0:
                skipped += 1
                continue
            attempted += 1
            time.sleep(0.08)
            long_res = source.fetch_position_rank(contract.variety_code, trade_date_dash, 2)
            short_res = source.fetch_position_rank(contract.variety_code, trade_date_dash, 3)
            if long_res.error:
                exchange_errors.append(f"{contract.variety_code} long: {long_res.error}")
            if short_res.error:
                exchange_errors.append(f"{contract.variety_code} short: {short_res.error}")
            long_rows = long_res.rows or []
            short_rows = short_res.rows or []
            fetched += len(long_rows) + len(short_rows)
            max_len = max(len(long_rows), len(short_rows))
            for idx in range(max_len):
                lr = long_rows[idx] if idx < len(long_rows) else {}
                sr = short_rows[idx] if idx < len(short_rows) else {}
                rank = idx + 1
                db.add(SeatRankRow(
                    trade_date=trade_date,
                    exchange=exchange,
                    variety=variety,
                    contract=str((lr or sr).get("symbolCode") or contract.variety_code),
                    rank=rank,
                    vol_party_name="",
                    vol=None,
                    vol_chg=None,
                    long_party_name=str(lr.get("companyName") or ""),
                    long_open_interest=safe_float(lr.get("volume")),
                    long_open_interest_chg=safe_float(lr.get("changes")),
                    short_party_name=str(sr.get("companyName") or ""),
                    short_open_interest=safe_float(sr.get("volume")),
                    short_open_interest_chg=safe_float(sr.get("changes")),
                    raw_json=json.dumps({"source": SOURCE, "long": lr, "short": sr}, ensure_ascii=False, default=str),
                ))
                saved += 1
        error_text = "; ".join(exchange_errors[:5]) if exchange_errors else None
        finish_crawler_run(run, rows=fetched, saved=saved, error=error_text)
        # Do not mark an exchange as failed if official rows already cover most varieties and fallback simply had nothing to add.
        update_data_gap(db, trade_date, exchange, "seat_rank_fallback", saved + skipped, error_text)
        total_rows += fetched
        total_saved += saved
        if error_text:
            errors.append(f"{exchange}: {error_text}")
        per_exchange[exchange] = {"contracts": len(contracts), "attempted": attempted, "skipped_existing": skipped, "rows": fetched, "saved": saved, "error": error_text}
    return {"rows": total_rows, "saved": total_saved, "error": "; ".join(errors) if errors else None, "exchanges": per_exchange}


def main_quhe_contracts(db: Session, exchange: str | None) -> list[QuheContract]:
    rows = db.scalars(select(QuheContract).where(QuheContract.is_main == True)).all()  # noqa: E712
    out = []
    seen = set()
    for row in rows:
        code = BOARD_TO_EXCHANGE.get(row.board_name)
        if exchange is not None and code != exchange:
            continue
        key = row.product_code.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def date8_from_ms(value: Any) -> str:
    try:
        if value is None:
            return ""
        dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


def snapshot_json(result) -> str:
    return json.dumps({"rows": result.rows, "row_count": len(result.rows), "error": result.error, "meta": result.meta}, ensure_ascii=False, default=str)


def dataframe_dict(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"value": str(type(data).__name__)}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            out[str(key)] = []
        elif hasattr(value, "where") and hasattr(value, "notnull") and hasattr(value, "to_dict"):
            out[str(key)] = value.where(value.notnull(), None).to_dict(orient="records")
        else:
            out[str(key)] = str(value)
    return out


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    return {"PTA": "TA"}.get(text, text)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None
