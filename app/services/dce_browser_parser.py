from __future__ import annotations

from typing import Any

from app.services.normalizer import normalize_seat_row

LONG_HINTS = ["持买", "买持", "多头", "买单", "long"]
SHORT_HINTS = ["持卖", "卖持", "空头", "卖单", "short"]
VOL_HINTS = ["成交", "成交量", "volume"]
PARTY_HINTS = ["会员", "会员简称", "期货公司", "公司"]
RANK_HINTS = ["名次", "排名", "rank"]
CHANGE_HINTS = ["增减", "变化", "较上一", "change"]


def parse_dce_table_candidate(candidate: dict[str, Any], *, exchange: str = "DCE") -> dict[str, Any]:
    """Dry-run parse one DCE browser table candidate into seat-like rows."""
    headers = [str(x or "").strip() for x in candidate.get("headers") or []]
    sample_rows = candidate.get("sample_rows") or []
    if not headers and sample_rows:
        headers = [str(x or "").strip() for x in sample_rows[0]]
        data_rows = sample_rows[1:]
    else:
        data_rows = sample_rows[1:] if sample_rows and row_matches_headers(sample_rows[0], headers) else sample_rows
    mapping = infer_column_mapping(headers)
    parsed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, row in enumerate(data_rows):
        try:
            raw = row_to_seat_raw(headers, row, mapping)
            normalized = normalize_seat_row(exchange, raw)
            err = validate_seat_like(normalized)
            if err:
                errors.append({"index": idx, "error": err, "raw": raw, "row": row})
                continue
            parsed.append(normalized)
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "error": f"{type(exc).__name__}: {exc}", "row": row})
    return {
        "status": "ok" if parsed and not errors else "partial" if parsed else "failed",
        "dry_run": True,
        "exchange": exchange,
        "input_rows": len(data_rows),
        "parsed_rows": len(parsed),
        "error_count": len(errors),
        "mapping": mapping,
        "headers": headers,
        "sample": strip_raw(parsed[:10]),
        "errors": errors[:10],
        "message": "DCE browser table parser dry-run only; database was not modified",
    }


def parse_dce_candidates(analysis: dict[str, Any]) -> dict[str, Any]:
    plans = analysis.get("parser_plan") or []
    table_candidates = [p for p in plans if p.get("type") == "html_table" and p.get("confidence") in {"medium", "high"}]
    results = [parse_dce_table_candidate(p) for p in table_candidates]
    parsed_total = sum(int(r.get("parsed_rows") or 0) for r in results)
    return {
        "status": "ok" if parsed_total else "no_rows",
        "dry_run": True,
        "exchange": "DCE",
        "tables_attempted": len(results),
        "parsed_rows": parsed_total,
        "results": results,
        "message": "DCE candidate parser dry-run; inspect mappings before promoting to seat_rank_rows",
    }


def infer_column_mapping(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    used: set[int] = set()

    def pick(name: str, hints: list[str], *, after: int | None = None) -> None:
        for i, h in enumerate(headers):
            if i in used:
                continue
            if after is not None and i <= after:
                continue
            if any(x.lower() in h.lower() for x in hints):
                mapping[name] = i
                used.add(i)
                return

    pick("rank", RANK_HINTS)
    pick("party", PARTY_HINTS)
    pick("vol", VOL_HINTS)
    pick("vol_chg", CHANGE_HINTS, after=mapping.get("vol"))
    pick("long_open_interest", LONG_HINTS)
    pick("long_open_interest_chg", CHANGE_HINTS, after=mapping.get("long_open_interest"))
    pick("short_open_interest", SHORT_HINTS)
    pick("short_open_interest_chg", CHANGE_HINTS, after=mapping.get("short_open_interest"))
    return mapping


def row_to_seat_raw(headers: list[str], row: Any, mapping: dict[str, int]) -> dict[str, Any]:
    values = [str(x or "").strip() for x in (row if isinstance(row, list) else [])]

    def val(name: str) -> str:
        idx = mapping.get(name)
        return values[idx] if idx is not None and idx < len(values) else ""

    party = val("party")
    return {
        "symbol": "DCE_BROWSER",
        "rank": val("rank"),
        "vol_party_name": party,
        "vol": val("vol"),
        "vol_chg": val("vol_chg"),
        "long_party_name": party,
        "long_open_interest": val("long_open_interest"),
        "long_open_interest_chg": val("long_open_interest_chg"),
        "short_party_name": party,
        "short_open_interest": val("short_open_interest"),
        "short_open_interest_chg": val("short_open_interest_chg"),
        "_headers": headers,
    }


def row_matches_headers(row: Any, headers: list[str]) -> bool:
    if not isinstance(row, list) or not headers:
        return False
    row_text = " ".join(str(x) for x in row)
    return sum(1 for h in headers if h and h in row_text) >= max(1, min(3, len(headers)))


def validate_seat_like(item: dict[str, Any]) -> str:
    if not item.get("variety"):
        return "missing variety"
    if not (item.get("long_party_name") or item.get("short_party_name") or item.get("vol_party_name")):
        return "missing party"
    if not any(item.get(k) is not None for k in ["vol", "long_open_interest", "short_open_interest"]):
        return "missing numeric seat value"
    return ""


def strip_raw(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        copied = dict(item)
        copied.pop("raw", None)
        out.append(copied)
    return out
