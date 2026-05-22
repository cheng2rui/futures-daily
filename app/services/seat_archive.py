from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings

FOCUS5_ALIASES = {
    "乾坤期货": ["乾坤期货", "乾坤", "高盛期货", "高盛"],
    "永安期货": ["永安期货", "永安"],
    "摩根大通": ["摩根大通", "摩根"],
    "瑞银期货": ["瑞银期货", "瑞银"],
    "混沌天成": ["混沌天成", "混沌"],
}


def _archive_root() -> Path:
    cfg = get_settings().seat_archive
    p = Path(cfg.path)
    if p.exists():
        return p
    fallback = Path("/Users/rey/.openclaw/workspace-rsstsx-bot/structured_archive")
    return fallback


def load_archive_summary(trade_date: str) -> dict[str, Any]:
    cfg = get_settings().seat_archive
    if not cfg.enabled:
        return empty_summary(trade_date, "disabled")
    root = _archive_root() / trade_date
    index_path = root / "index.json"
    if not index_path.exists():
        return empty_summary(trade_date, f"archive not found: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    varieties = []
    for item in index.get("varieties", []):
        fp = root / item.get("file", "")
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            varieties.append(compact_variety(data))
        except Exception:
            continue

    net_delta_top = sorted(varieties, key=lambda x: abs(x.get("netDelta") or 0), reverse=True)[:15]
    long_bias = sorted([v for v in varieties if (v.get("netDelta") or 0) > 0], key=lambda x: x.get("netDelta") or 0, reverse=True)[:10]
    short_bias = sorted([v for v in varieties if (v.get("netDelta") or 0) < 0], key=lambda x: x.get("netDelta") or 0)[:10]
    ratio_extreme = sorted(varieties, key=lambda x: abs(float_or_one(x.get("longShortRatio")) - 1), reverse=True)[:10]
    concentration = sorted(varieties, key=lambda x: max(x.get("longCR5") or 0, x.get("shortCR5") or 0), reverse=True)[:10]
    focus5 = build_focus5(varieties)

    return {
        "date": trade_date,
        "source": "rsstsx_structured_archive",
        "status": "ok",
        "count": len(varieties),
        "generatedAt": index.get("generatedAt"),
        "varieties": varieties,
        "net_delta_top": net_delta_top,
        "long_bias": long_bias,
        "short_bias": short_bias,
        "ratio_extreme": ratio_extreme,
        "concentration": concentration,
        "focus5": focus5,
    }


def compact_variety(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": data.get("name"),
        "displayName": data.get("displayName") or data.get("name"),
        "exchange": data.get("exchange"),
        "vol": data.get("vol"),
        "longTotal": data.get("longTotal"),
        "shortTotal": data.get("shortTotal"),
        "longShortRatio": data.get("longShortRatio"),
        "longCR5": data.get("longCR5"),
        "shortCR5": data.get("shortCR5"),
        "longDeltaSum": data.get("longDeltaSum"),
        "shortDeltaSum": data.get("shortDeltaSum"),
        "netDelta": data.get("netDelta"),
        "netDir": data.get("netDir"),
        "topLongByDelta": clean_member_row(data.get("topLongByDelta")),
        "topShortByDelta": clean_member_row(data.get("topShortByDelta")),
        "longRows": [clean_member_row(x) for x in (data.get("longRows") or [])[:20]],
        "shortRows": [clean_member_row(x) for x in (data.get("shortRows") or [])[:20]],
    }


def clean_member_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    return {"rank": row.get("rank"), "member": row.get("member"), "vol": row.get("vol"), "delta": row.get("delta")}


def build_focus5(varieties: list[dict[str, Any]]) -> dict[str, Any]:
    by_seat: dict[str, list[dict[str, Any]]] = {seat: [] for seat in FOCUS5_ALIASES}
    combined_by_variety: dict[str, dict[str, Any]] = {}
    for v in varieties:
        for canonical, aliases in FOCUS5_ALIASES.items():
            long = sum((r.get("vol") or 0) for r in v.get("longRows", []) if member_match(r.get("member"), aliases))
            short = sum((r.get("vol") or 0) for r in v.get("shortRows", []) if member_match(r.get("member"), aliases))
            long_delta = sum((r.get("delta") or 0) for r in v.get("longRows", []) if member_match(r.get("member"), aliases))
            short_delta = sum((r.get("delta") or 0) for r in v.get("shortRows", []) if member_match(r.get("member"), aliases))
            if long or short or long_delta or short_delta:
                row = {
                    "seat": canonical,
                    "variety": v.get("displayName"),
                    "exchange": v.get("exchange"),
                    "netVol": long - short,
                    "netDelta": long_delta - short_delta,
                    "longVol": long,
                    "shortVol": short,
                    "longDelta": long_delta,
                    "shortDelta": short_delta,
                }
                by_seat[canonical].append(row)
                key = str(v.get("displayName"))
                agg = combined_by_variety.setdefault(key, {"variety": key, "exchange": v.get("exchange"), "netDelta": 0, "netVol": 0, "seats": []})
                agg["netDelta"] += row["netDelta"]
                agg["netVol"] += row["netVol"]
                agg["seats"].append({"seat": canonical, "netDelta": row["netDelta"], "netVol": row["netVol"]})
    for seat in by_seat:
        by_seat[seat] = sorted(by_seat[seat], key=lambda x: abs(x.get("netDelta") or 0), reverse=True)[:10]
    combined = sorted(combined_by_variety.values(), key=lambda x: abs(x.get("netDelta") or 0), reverse=True)[:15]
    return {"by_seat": by_seat, "combined_by_variety": combined}


def member_match(member: str | None, aliases: list[str]) -> bool:
    text = member or ""
    return any(alias in text for alias in aliases)


def float_or_one(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 1.0


def available_archive_dates() -> list[str]:
    root = _archive_root()
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8])


def load_archive_history(trade_date: str, days: int = 5, seat: str | None = None, variety: str | None = None) -> dict[str, Any]:
    dates = [d for d in available_archive_dates() if d <= trade_date][-max(1, min(days, 30)):]
    daily = []
    for d in dates:
        summary = load_archive_summary(d)
        compact = {
            "date": d,
            "status": summary.get("status"),
            "count": summary.get("count", 0),
            "net_delta_top": filter_varieties(summary.get("net_delta_top", []), variety)[:8],
            "focus5_combined": filter_focus_combined(summary.get("focus5", {}).get("combined_by_variety", []), seat, variety)[:8],
            "focus5_by_seat": filter_focus_by_seat(summary.get("focus5", {}).get("by_seat", {}), seat, variety),
        }
        daily.append(compact)
    return {
        "end_date": trade_date,
        "days": len(daily),
        "available_dates": dates,
        "seat": seat or "",
        "variety": variety or "",
        "daily": daily,
        "trend": build_trend(daily, seat, variety),
    }


def filter_varieties(rows: list[dict[str, Any]], variety: str | None) -> list[dict[str, Any]]:
    if not variety:
        return rows
    key = variety.upper()
    return [r for r in rows if key in str(r.get("name") or r.get("displayName") or "").upper()]


def filter_focus_combined(rows: list[dict[str, Any]], seat: str | None, variety: str | None) -> list[dict[str, Any]]:
    result = rows
    if variety:
        key = variety.upper()
        result = [r for r in result if key in str(r.get("variety") or "").upper()]
    if seat:
        key = seat
        result = [r for r in result if any(key in str(s.get("seat") or "") for s in r.get("seats", []))]
    return result


def filter_focus_by_seat(by_seat: dict[str, list[dict[str, Any]]], seat: str | None, variety: str | None) -> dict[str, list[dict[str, Any]]]:
    items = by_seat.items()
    if seat:
        items = [(k, v) for k, v in items if seat in k]
    out: dict[str, list[dict[str, Any]]] = {}
    for k, rows in items:
        if variety:
            key = variety.upper()
            rows = [r for r in rows if key in str(r.get("variety") or "").upper()]
        out[k] = rows[:6]
    return out


def build_trend(daily: list[dict[str, Any]], seat: str | None, variety: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in daily:
        if seat:
            for seat_name, items in day.get("focus5_by_seat", {}).items():
                for item in items:
                    rows.append({"date": day["date"], "seat": seat_name, "variety": item.get("variety"), "exchange": item.get("exchange"), "netDelta": item.get("netDelta"), "netVol": item.get("netVol")})
        else:
            for item in day.get("focus5_combined", [])[:5]:
                rows.append({"date": day["date"], "seat": "Focus5合计", "variety": item.get("variety"), "exchange": item.get("exchange"), "netDelta": item.get("netDelta"), "netVol": item.get("netVol")})
    return rows


def empty_summary(trade_date: str, reason: str) -> dict[str, Any]:
    return {"date": trade_date, "source": "rsstsx_structured_archive", "status": "empty", "reason": reason, "count": 0, "net_delta_top": [], "focus5": {"by_seat": {}, "combined_by_variety": []}}
