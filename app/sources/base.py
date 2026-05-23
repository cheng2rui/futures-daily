from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderCapability:
    """Describe one fetch capability exposed by a futures data provider."""

    kind: str
    exchanges: list[str] = field(default_factory=list)
    status: str = "available"
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "exchanges": self.exchanges,
            "status": self.status,
            "note": self.note,
        }


@dataclass(frozen=True)
class FetchResult:
    exchange: str
    kind: str
    rows: list[dict[str, Any]]
    error: str | None = None
    source: str = ""

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "kind": self.kind,
            "rows": self.rows,
            "row_count": len(self.rows),
            "error": self.error,
            "source": self.source,
        }


class FuturesDataProvider(Protocol):
    """Unified adapter protocol for futures daily data sources.

    Implementations may wrap AkShare, manual imports, licensed Wind/iFinD
    connectors, or exchange official endpoints. Service layers should depend on
    this protocol rather than vendor-specific SDKs.
    """

    name: str

    def capabilities(self) -> list[ProviderCapability]:
        ...

    def fetch_daily(self, trade_date: str, exchange: str) -> FetchResult:
        ...

    def fetch_seat_rank(self, trade_date: str, exchange: str) -> FetchResult:
        ...
