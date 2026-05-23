from __future__ import annotations

from app.sources.registry import get_market_provider, list_provider_capabilities


def check() -> None:
    providers = list_provider_capabilities()
    names = {item["name"] for item in providers}
    assert "akshare" in names
    provider = get_market_provider("akshare")
    kinds = {cap.kind for cap in provider.capabilities()}
    assert "daily" in kinds
    assert "seat_rank" in kinds


if __name__ == "__main__":
    check()
    print("ok")
