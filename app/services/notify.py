from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings


@dataclass
class NotifyEvent:
    type: str
    title: str
    message: str
    payload: dict[str, Any] | None = None


async def dispatch(event: NotifyEvent) -> list[dict[str, Any]]:
    """Dispatch notification events.

    MVP keeps channel adapters as stubs so config/API shape is stable.
    """
    settings = get_settings().notify
    results: list[dict[str, Any]] = []
    for name in ["telegram", "wecom", "wechatbot"]:
        cfg = getattr(settings, name)
        if not cfg.enabled:
            results.append({"channel": name, "skipped": True})
            continue
        results.append({"channel": name, "skipped": True, "reason": "adapter not implemented yet"})
    return results
