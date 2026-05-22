from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yaml

from app.config import get_settings
from app.services.notify import NotifyEvent, dispatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings():
    settings = get_settings()
    data = settings.model_dump()
    # Do not expose secrets when notification channels are configured later.
    for channel in data.get("notify", {}).values():
        if channel.get("bot_token"):
            channel["bot_token"] = "***"
        if channel.get("token"):
            channel["token"] = "***"
    provider = data.get("assistant", {}).get("provider", {})
    if provider.get("api_key"):
        provider["api_key"] = "***"
    return data


class TelegramNotifyUpdate(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None
    chat_id: str | None = None


class WeChatBotNotifyUpdate(BaseModel):
    enabled: bool | None = None
    webhook_url: str | None = None
    token: str | None = None
    chat_id: str | None = None
    claw_base_url: str | None = None
    claw_target: str | None = None


@router.patch("/notify/telegram")
def update_telegram_notify(patch: TelegramNotifyUpdate):
    return _update_notify_channel("telegram", patch.model_dump(exclude_unset=True), ["bot_token"])


@router.patch("/notify/wechatbot")
def update_wechatbot_notify(patch: WeChatBotNotifyUpdate):
    return _update_notify_channel("wechatbot", patch.model_dump(exclude_unset=True), ["token"])


@router.post("/notify/test")
async def test_notify():
    results = await dispatch(NotifyEvent(type="notify_test", title="通知测试", message="【期货日报】通知测试\n如果你看到这条消息，说明当前通知通道已连通。"))
    failed = [x for x in results if x.get("ok") is False]
    sent = [x for x in results if x.get("ok") is True]
    skipped = [x for x in results if x.get("skipped")]
    return {"ok": not failed, "sent": len(sent), "skipped": len(skipped), "failed": len(failed), "dispatch": results}


def _update_notify_channel(channel: str, incoming: dict[str, Any], secret_keys: list[str]):
    path = Path(os.getenv("FUTURES_DAILY_CONFIG", "config/config.yaml"))
    data = _read_yaml(path)
    notify = data.setdefault("notify", {})
    channel_data = notify.setdefault(channel, {})
    for key in secret_keys:
        if incoming.get(key) == "***":
            incoming.pop(key, None)
    for key, value in incoming.items():
        if value is not None:
            channel_data[key] = value
    _write_yaml(path, data)
    get_settings.cache_clear()
    return read_settings().get("notify", {}).get(channel, {})


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"read config failed: {exc}") from exc


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"write config failed: {exc}") from exc
