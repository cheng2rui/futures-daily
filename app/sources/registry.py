from __future__ import annotations

from app.sources.akshare_source import AkShareSource
from app.sources.base import FuturesDataProvider


_PROVIDER_FACTORIES = {
    "akshare": AkShareSource,
    # Reserved names for legal/licensed or local adapters. They are intentionally
    # not wired to private SDKs here; implementation can be added after the user
    # provides legitimate credentials/data exports.
    "wind": None,
    "ifind": None,
    "manual_import": None,
}


def list_provider_capabilities() -> list[dict]:
    rows: list[dict] = []
    for name, factory in _PROVIDER_FACTORIES.items():
        if factory is None:
            rows.append({
                "name": name,
                "status": "reserved",
                "capabilities": [],
                "note": "Reserved adapter slot; not enabled without licensed credentials or local import files.",
            })
            continue
        provider = factory()
        rows.append({
            "name": name,
            "status": "available",
            "capabilities": [x.as_dict() for x in provider.capabilities()],
            "note": "Default configured provider." if name == "akshare" else "",
        })
    return rows


def get_market_provider(name: str = "akshare") -> FuturesDataProvider:
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"provider not available: {name}")
    return factory()
