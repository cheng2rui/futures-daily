from __future__ import annotations

from typing import Any

from app.services.seat_archive import FOCUS5_ALIASES, load_archive_summary
from app.sources.base import FetchResult, ProviderCapability


class RsstsxArchiveSource:
    """Structured seat archive provider backed by workspace-rsstsx-bot output."""

    name = "rsstsx_archive"

    def capabilities(self) -> list[ProviderCapability]:
        return [ProviderCapability(kind="seat_archive_signal", exchanges=["DCE", "CZCE", "SHFE", "CFFEX", "GFEX", "INE"], status="available", note="Focus5/CR5/long-short ratio/net-delta signals from structured rsstsx archives.")]

    def fetch_daily(self, trade_date: str, exchange: str) -> FetchResult:
        return FetchResult(exchange=exchange, kind="daily", rows=[], error="rsstsx archive does not provide daily bars", source=self.name)

    def fetch_seat_rank(self, trade_date: str, exchange: str) -> FetchResult:
        summary = load_archive_summary(trade_date)
        if summary.get("status") != "ok":
            return FetchResult(exchange=exchange, kind="seat_rank", rows=[], error=summary.get("reason") or "archive unavailable", source=self.name)
        rows = [to_provider_row(v) for v in summary.get("varieties", []) if str(v.get("exchange") or "").upper() == exchange.upper()]
        return FetchResult(exchange=exchange, kind="seat_rank", rows=rows, source=self.name)

    def fetch_signals(self, trade_date: str) -> dict[str, Any]:
        summary = load_archive_summary(trade_date)
        if summary.get("status") != "ok":
            return summary
        return {
            "date": trade_date,
            "source": self.name,
            "status": "ok",
            "count": summary.get("count", 0),
            "focus5_aliases": FOCUS5_ALIASES,
            "focus5": summary.get("focus5", {}),
            "net_delta_top": summary.get("net_delta_top", []),
            "ratio_extreme": summary.get("ratio_extreme", []),
            "concentration": summary.get("concentration", []),
        }


def to_provider_row(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "variety": v.get("name") or v.get("displayName"),
        "exchange": v.get("exchange"),
        "long_short_ratio": v.get("longShortRatio"),
        "long_cr5": v.get("longCR5"),
        "short_cr5": v.get("shortCR5"),
        "net_delta": v.get("netDelta"),
        "net_dir": v.get("netDir"),
        "top_long_by_delta": v.get("topLongByDelta"),
        "top_short_by_delta": v.get("topShortByDelta"),
        "long_rows": v.get("longRows", []),
        "short_rows": v.get("shortRows", []),
    }
