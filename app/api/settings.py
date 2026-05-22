from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings():
    settings = get_settings()
    data = settings.model_dump()
    # Do not expose secrets when notification channels are configured later.
    for channel in data.get("notify", {}).values():
        if channel.get("bot_token"):
            channel["bot_token"] = "***"
    provider = data.get("assistant", {}).get("provider", {})
    if provider.get("api_key"):
        provider["api_key"] = "***"
    return data
