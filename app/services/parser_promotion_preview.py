from __future__ import annotations

from typing import Any

from app.models import SourceFile
from app.services.parser_promotion_guard import evaluate_parser_promotion
from app.services.raw_replay import replay_source_row


def build_promotion_preview(source_file: SourceFile, *, sample_limit: int = 50) -> dict[str, Any]:
    """Build a guarded preview of rows that a future promotion would insert.

    No database writes happen here. The caller gets a deterministic preview plus
    the promotion guard decision. Future write endpoints must require
    guard.allowed=true and an explicit user/operator action.
    """
    replay = replay_source_row(source_file, sample_limit=sample_limit)
    guard = replay.get("promotion_guard") or evaluate_parser_promotion(replay.get("parser_dry_run"))
    dry = replay.get("parser_dry_run") or {}
    rows = collect_preview_rows(dry, limit=sample_limit) if guard.get("allowed") else []
    return {
        "file": replay.get("file"),
        "dry_run": True,
        "would_write": False,
        "status": "ready" if guard.get("allowed") else "blocked",
        "promotion_guard": guard,
        "preview_rows": rows,
        "preview_count": len(rows),
        "source_replay_status": replay.get("status"),
        "message": "Guard PASS: preview only; no database rows were written." if guard.get("allowed") else "Guard BLOCKED: promotion preview suppressed; no database rows were written.",
    }


def collect_preview_rows(parser_dry_run: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    results = parser_dry_run.get("results") if isinstance(parser_dry_run.get("results"), list) else [parser_dry_run]
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        for item in result.get("sample") or []:
            if not isinstance(item, dict):
                continue
            rows.append(seat_rank_preview_row(item))
            if len(rows) >= limit:
                return rows
    return rows


def seat_rank_preview_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": "<from_source_file>",
        "exchange": "DCE",
        "variety": item.get("variety") or "DCE_BROWSER",
        "contract": item.get("contract") or "",
        "rank": item.get("rank"),
        "vol_party_name": item.get("vol_party_name") or "",
        "vol": item.get("vol"),
        "vol_chg": item.get("vol_chg"),
        "long_party_name": item.get("long_party_name") or "",
        "long_open_interest": item.get("long_open_interest"),
        "long_open_interest_chg": item.get("long_open_interest_chg"),
        "short_party_name": item.get("short_party_name") or "",
        "short_open_interest": item.get("short_open_interest"),
        "short_open_interest_chg": item.get("short_open_interest_chg"),
    }
