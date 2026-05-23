from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceFile
from app.services.normalizer import normalize_daily_row, normalize_seat_row
from app.services.raw_archive import read_archive, source_file_item

Normalizer = Callable[[str, dict[str, Any]], dict[str, Any]]

SUPPORTED_KINDS: dict[str, Normalizer] = {
    "daily": normalize_daily_row,
    "seat_rank": normalize_seat_row,
}


def replay_source_file(db: Session, file_id: int, *, sample_limit: int = 10) -> dict[str, Any]:
    row = db.scalar(select(SourceFile).where(SourceFile.id == file_id))
    if not row:
        return {"error": "not_found", "file_id": file_id}
    return replay_source_row(row, sample_limit=sample_limit)


def replay_source_row(row: SourceFile, *, sample_limit: int = 10) -> dict[str, Any]:
    loaded = read_archive(row)
    if not loaded.get("exists"):
        return {"file": source_file_item(row), "status": "missing_file", "error": "archive file not found"}
    payload = loaded.get("payload")
    rows = extract_rows(payload)
    normalizer = SUPPORTED_KINDS.get(row.kind)
    if not normalizer:
        return {
            "file": source_file_item(row),
            "status": "unsupported",
            "kind": row.kind,
            "input_rows": len(rows),
            "message": f"raw replay parser for {row.kind} is not implemented yet",
            "sample_raw": rows[:sample_limit],
        }

    parsed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows):
        if not isinstance(raw, dict):
            errors.append({"index": idx, "error": "row is not an object", "row": raw})
            continue
        try:
            item = normalizer(row.exchange, raw)
            validation_error = validate_normalized(row.kind, item)
            if validation_error:
                errors.append({"index": idx, "error": validation_error, "row": raw, "parsed": item})
                continue
            parsed.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "error": f"{type(exc).__name__}: {exc}", "row": raw})

    parsed_rows = len(parsed)
    success_rate = round(parsed_rows / len(rows) * 100, 1) if rows else 0
    return {
        "file": source_file_item(row),
        "status": "ok" if parsed and not errors else "partial" if parsed else "failed",
        "kind": row.kind,
        "dry_run": True,
        "input_rows": len(rows),
        "parsed_rows": parsed_rows,
        "skipped_rows": len(errors),
        "error_count": len(errors),
        "success_rate": success_rate,
        "errors": errors[:20],
        "sample": strip_raw(parsed[:sample_limit]),
        "stats": build_stats(row.kind, parsed),
        "message": "dry-run only; database was not modified",
    }


def extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return rows
        # Official warehouse archive stores a dict of symbol -> rows under rows.
        if isinstance(rows, dict):
            flattened: list[Any] = []
            for symbol, items in rows.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            flattened.append({"_archive_symbol": symbol, **item})
                        else:
                            flattened.append(item)
            return flattened
    if isinstance(payload, list):
        return payload
    return []


def validate_normalized(kind: str, item: dict[str, Any]) -> str:
    if kind == "daily":
        if not item.get("contract"):
            return "missing contract"
        if not item.get("symbol"):
            return "missing symbol"
        return ""
    if kind == "seat_rank":
        if not item.get("variety"):
            return "missing variety"
        if not (item.get("long_party_name") or item.get("short_party_name") or item.get("vol_party_name")):
            return "missing seat party"
        return ""
    return ""


def strip_raw(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        copied = dict(item)
        copied.pop("raw", None)
        out.append(copied)
    return out


def build_stats(kind: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    if kind == "daily":
        symbols = sorted({str(x.get("symbol") or "") for x in items if x.get("symbol")})
        contracts = sorted({str(x.get("contract") or "") for x in items if x.get("contract")})
        return {"symbols": len(symbols), "contracts": len(contracts), "sample_symbols": symbols[:20]}
    if kind == "seat_rank":
        varieties = sorted({str(x.get("variety") or "") for x in items if x.get("variety")})
        parties = sorted({str(x.get("long_party_name") or "") for x in items if x.get("long_party_name")})
        return {"varieties": len(varieties), "long_parties": len(parties), "sample_varieties": varieties[:20]}
    return {}
