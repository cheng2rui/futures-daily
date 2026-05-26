from __future__ import annotations

from typing import Any, Callable
import html as html_lib
import re
from urllib.parse import urljoin

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

BROWSER_PROBE_SUFFIX = "_browser_probe"


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
    if row.kind.endswith(BROWSER_PROBE_SUFFIX):
        return replay_browser_probe(row, payload, sample_limit=sample_limit)
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


def replay_browser_probe(row: SourceFile, payload: Any, *, sample_limit: int = 10) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "file": source_file_item(row),
            "status": "failed",
            "kind": row.kind,
            "dry_run": True,
            "input_rows": 0,
            "parsed_rows": 0,
            "error_count": 1,
            "errors": [{"error": "browser probe payload is not an object"}],
            "message": "dry-run only; database was not modified",
        }
    html = str(payload.get("html") or "")
    status = "ok" if payload.get("ok") and html else "failed"
    signals = browser_probe_signals(html)
    candidates = browser_probe_candidates(html, base_url=str(payload.get("url") or payload.get("requested_url") or ""), limit=sample_limit)
    error = str(payload.get("error") or "")
    return {
        "file": source_file_item(row),
        "status": status,
        "kind": row.kind,
        "dry_run": True,
        "input_rows": 1 if payload else 0,
        "parsed_rows": 1 if status == "ok" else 0,
        "skipped_rows": 0 if status == "ok" else 1,
        "error_count": 0 if status == "ok" else 1,
        "success_rate": 100.0 if status == "ok" else 0,
        "errors": [] if status == "ok" else [{"error": error or "browser probe failed"}],
        "sample": [{
            "url": payload.get("url") or payload.get("requested_url"),
            "status": payload.get("status"),
            "title": payload.get("title"),
            "html_length": payload.get("html_length") or len(html),
            "webdriver": payload.get("webdriver"),
            "user_agent": payload.get("user_agent"),
            "signals": signals,
            "candidates": candidates,
        }][:sample_limit],
        "stats": {
            "title": payload.get("title") or "",
            "html_length": payload.get("html_length") or len(html),
            "contains_table": signals.get("contains_table", False),
            "contains_excel": signals.get("contains_excel", False),
            "contains_position_keywords": signals.get("contains_position_keywords", False),
            "table_candidates": len(candidates.get("tables", [])),
            "excel_links": len(candidates.get("excel_links", [])),
            "keyword_blocks": len(candidates.get("keyword_blocks", [])),
        },
        "message": "browser probe replay only; use exchange-specific parser before promoting rows",
    }


def browser_probe_signals(html: str) -> dict[str, Any]:
    low = html.lower()
    return {
        "contains_table": "<table" in low,
        "contains_excel": any(x in low for x in [".xls", ".xlsx", "excel"]),
        "contains_position_keywords": any(x in html for x in ["持仓", "成交", "会员", "排名", "龙虎榜"]),
        "challenge_like": any(x in low for x in ["captcha", "cloudflare", "challenge", "forbidden", "访问过于频繁"]),
    }


def browser_probe_candidates(html: str, *, base_url: str = "", limit: int = 10) -> dict[str, Any]:
    """Extract parser candidates from a browser probe HTML snapshot.

    This is intentionally heuristic and dry-run only: it points future
    exchange-specific parsers at promising table/link/text regions without
    normalizing them into official rows yet.
    """
    return {
        "tables": extract_html_tables(html, limit=limit),
        "excel_links": extract_excel_links(html, base_url=base_url, limit=limit),
        "keyword_blocks": extract_keyword_blocks(html, limit=limit),
    }


def extract_html_tables(html: str, *, limit: int = 10) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for idx, match in enumerate(re.finditer(r"(?is)<table\b.*?</table>", html)):
        table_html = match.group(0)
        text = html_to_text(table_html)
        headers = re.findall(r"(?is)<th\b[^>]*>(.*?)</th>", table_html)
        rows = re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", table_html)
        row_samples: list[list[str]] = []
        for row in rows[:5]:
            cells = re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row)
            row_samples.append([html_to_text(c) for c in cells[:12]])
        tables.append({
            "index": idx,
            "char_start": match.start(),
            "char_end": match.end(),
            "headers": [html_to_text(x) for x in headers[:20]],
            "row_count_estimate": len(rows),
            "sample_rows": row_samples,
            "text_preview": text[:600],
            "contains_position_keywords": any(x in text for x in ["持仓", "成交", "会员", "排名", "龙虎榜"]),
        })
        if len(tables) >= limit:
            break
    return tables


def extract_excel_links(html: str, *, base_url: str = "", limit: int = 10) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for match in re.finditer(r"(?is)<a\b([^>]*?)>(.*?)</a>", html):
        attrs, label_html = match.group(1), match.group(2)
        href_match = re.search(r'''(?is)href\s*=\s*["']([^"']+)["']''', attrs)
        if not href_match:
            continue
        href = html_lib.unescape(href_match.group(1).strip())
        label = html_to_text(label_html)
        haystack = f"{href} {label}".lower()
        if not any(x in haystack for x in [".xls", ".xlsx", "excel", "csv", "持仓", "排名"]):
            continue
        links.append({
            "href": href,
            "absolute_url": urljoin(base_url, href) if base_url else href,
            "label": label,
            "char_start": match.start(),
        })
        if len(links) >= limit:
            break
    return links


def extract_keyword_blocks(html: str, *, limit: int = 10) -> list[dict[str, Any]]:
    text = html_to_text(html)
    keywords = ["持仓", "成交", "会员", "排名", "龙虎榜", "多头", "空头", "期货公司"]
    blocks: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for kw in keywords:
        for match in re.finditer(re.escape(kw), text):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 220)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            blocks.append({"keyword": kw, "char_start": start, "char_end": end, "text": text[start:end]})
            if len(blocks) >= limit:
                return blocks
    return blocks


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</tr>|</td>|</th>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
