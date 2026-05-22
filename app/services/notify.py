from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import time

import requests

from app.config import get_settings


@dataclass
class NotifyEvent:
    type: str
    title: str
    message: str
    payload: dict[str, Any] | None = None


async def dispatch(event: NotifyEvent) -> list[dict[str, Any]]:
    """Dispatch notification events to enabled channels."""
    settings = get_settings().notify
    results: list[dict[str, Any]] = []
    for name in ["telegram", "wecom", "wechatbot"]:
        cfg = getattr(settings, name)
        if not cfg.enabled:
            results.append({"channel": name, "skipped": True})
            continue
        try:
            if name == "telegram":
                results.append(send_telegram(cfg.bot_token, cfg.chat_id, event))
            elif name == "wechatbot":
                results.append(send_wechatbot(cfg, event))
            else:
                results.append({"channel": name, "skipped": True, "reason": "adapter not implemented yet"})
        except Exception as exc:  # noqa: BLE001
            results.append({"channel": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return results


def send_telegram(bot_token: str, chat_id: str, event: NotifyEvent) -> dict[str, Any]:
    if not bot_token or not chat_id:
        return {"channel": "telegram", "skipped": True, "reason": "missing bot_token/chat_id"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": event.message, "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code >= 400:
        return {"channel": "telegram", "ok": False, "status_code": r.status_code, "body": r.text[:500]}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    return {"channel": "telegram", "ok": True, "response": body}


def send_wechatbot(cfg: Any, event: NotifyEvent) -> dict[str, Any]:
    """Send text to WeChatBot-compatible endpoints.

    Supports two modes:
    - webhook_url: a self-hosted WeChatBot/iLink forwarding endpoint.
    - claw_base_url + token + claw_target: WeChat Claw/iLink direct sendmessage API.
    """
    text = _plain_text(event.message)
    target = (cfg.chat_id or cfg.claw_target or "").strip()
    if cfg.webhook_url:
        return _send_wechatbot_webhook(cfg.webhook_url, text, target, cfg.token)
    if cfg.token and target:
        return _send_wechat_claw(cfg.claw_base_url, cfg.token, target, text)
    return {"channel": "wechatbot", "skipped": True, "reason": "missing webhook_url or token/target"}


def _plain_text(text: str) -> str:
    return (text or "").replace("<b>", "").replace("</b>", "").replace("<br>", "\n")


def _response_body(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def _send_wechatbot_webhook(webhook_url: str, text: str, target: str, token: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text, "content": text, "msg_type": "text"}
    if target:
        payload["target"] = target
        payload["to_user"] = target
    if token:
        payload["token"] = token
    resp = requests.post(webhook_url, json=payload, timeout=15)
    body = _response_body(resp)
    if resp.status_code >= 400:
        return {"channel": "wechatbot", "ok": False, "status_code": resp.status_code, "body": body}
    return {"channel": "wechatbot", "ok": _is_ok_body(body), "response": body}


def _send_wechat_claw(base_url: str, token: str, target: str, text: str) -> dict[str, Any]:
    url = urljoin((base_url or "https://ilinkai.weixin.qq.com").rstrip("/") + "/", "ilink/bot/sendmessage")
    headers = {"Authorization": f"Bearer {token}", "AuthorizationType": "ilink_bot_token"}
    candidates = [target]
    if target.endswith("@im.wechat"):
        candidates.append(target[:-10])
    elif "@" not in target:
        candidates.append(target + "@im.wechat")

    last: dict[str, Any] | None = None
    for to_user in dict.fromkeys(candidates):
        client_id = f"fd-{int(time.time() * 1000)}"
        payloads = [
            {"to_user": to_user, "msg_type": "text", "text": {"content": text}},
            {"to_user": to_user, "msg_type": "text", "text": text},
            {"to": to_user, "type": "text", "content": text},
            {
                "msg": {
                    "to_user_id": to_user,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                }
            },
        ]
        for payload in payloads:
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            body = _response_body(resp)
            last = {"channel": "wechatbot", "ok": _is_ok_body(body), "status_code": resp.status_code, "response": body}
            if resp.status_code < 400 and last["ok"]:
                return last
    return last or {"channel": "wechatbot", "ok": False, "error": "send failed"}


def _is_ok_body(body: Any) -> bool:
    if not isinstance(body, dict):
        return True
    values = [body.get(k) for k in ("ok", "success")]
    if any(v is True for v in values):
        return True
    if any(v is False for v in values):
        return False
    status = str(body.get("status") or body.get("state") or "").strip().lower()
    if status in ("ok", "success", "succeed", "sent"):
        return True
    error = str(body.get("error") or body.get("error_msg") or body.get("detail") or "").strip().lower()
    if error and error not in ("ok", "success", "succeed", "sent"):
        return False
    code = body.get("errcode", body.get("error_code", body.get("code")))
    if code in (0, "0", 200, "200", None):
        msg = str(body.get("errmsg", body.get("message", ""))).lower()
        return msg in ("", "ok", "success", "succeed", "sent") or "success" in msg
    return False
