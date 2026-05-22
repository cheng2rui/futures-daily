from types import SimpleNamespace

from app.services.notify import NotifyEvent, _is_ok_body, send_wechatbot


def check() -> None:
    assert _is_ok_body({"ok": True}) is True
    assert _is_ok_body({"success": True}) is True
    assert _is_ok_body({"status": "ok"}) is True
    assert _is_ok_body({"code": 200}) is True
    assert _is_ok_body({"errcode": 0, "errmsg": "ok"}) is True
    assert _is_ok_body({"ok": False}) is False
    assert _is_ok_body({"error": "bad token"}) is False

    calls = []

    class Resp:
        status_code = 200
        text = '{"ok": true}'

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls.append((url, json, headers, timeout))
        return Resp()

    import app.services.notify as notify

    old_post = notify.requests.post
    notify.requests.post = fake_post
    try:
        webhook_cfg = SimpleNamespace(
            webhook_url="http://wechat.local/send",
            token="tok",
            chat_id="wxid_1",
            claw_target="",
            claw_base_url="https://ilinkai.weixin.qq.com",
        )
        result = send_wechatbot(webhook_cfg, NotifyEvent(type="daily_report", title="t", message="hello<br>world"))
        assert result["ok"] is True
        assert calls[-1][1]["text"] == "hello\nworld"
        assert calls[-1][1]["target"] == "wxid_1"

        claw_cfg = SimpleNamespace(
            webhook_url="",
            token="tok",
            chat_id="wxid_1",
            claw_target="",
            claw_base_url="https://ilinkai.weixin.qq.com",
        )
        result = send_wechatbot(claw_cfg, NotifyEvent(type="daily_report", title="t", message="daily"))
        assert result["ok"] is True
        assert calls[-1][0].endswith("/ilink/bot/sendmessage")
        assert calls[-1][2]["AuthorizationType"] == "ilink_bot_token"
    finally:
        notify.requests.post = old_post


if __name__ == "__main__":
    check()
    print("ok")
