from __future__ import annotations

import json
import subprocess
from typing import Any

from sqlalchemy.orm import Session

from app.services.browser.cloakbrowser import cloakbrowser_info, runtime_from_settings
from app.services.raw_archive import archive_payload

OFFICIAL_PROBE_URLS = {
    "DCE": "https://www.dce.com.cn/",
    "CZCE": "https://www.czce.com.cn/",
    "SHFE": "https://www.shfe.com.cn/",
    "CFFEX": "https://www.cffex.com.cn/",
    "GFEX": "https://www.gfex.com.cn/",
    "INE": "https://www.ine.cn/",
}


def official_probe_url(exchange: str) -> str:
    return OFFICIAL_PROBE_URLS.get(str(exchange).upper(), "")


def probe_official_page(
    db: Session,
    *,
    trade_date: str,
    exchange: str,
    kind: str = "seat_rank",
    url: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Low-frequency CloakBrowser probe for an exchange official page.

    v0.5.14 intentionally archives raw browser observations only. It does not
    promote parsed data. Parser replay / exchange-specific adapters can consume
    the archived payload later.
    """
    exchange = exchange.upper()
    rt = runtime_from_settings()
    info = cloakbrowser_info(rt)
    target = url or official_probe_url(exchange)
    source_name = source or f"{exchange.lower()}_official_cloakbrowser"
    if not target:
        payload = {"ok": False, "exchange": exchange, "kind": kind, "error": "official probe URL not configured"}
        row = archive_payload(db, trade_date=trade_date, exchange=exchange, kind=f"{kind}_browser_probe", source=source_name, payload=payload, rows=0, error=payload["error"])
        return {"ok": False, "archive_id": row.id, "source_file": row.path, "error": payload["error"], "info": info}
    if not info.get("available"):
        payload = {"ok": False, "exchange": exchange, "kind": kind, "url": target, "error": info.get("reason") or "cloakbrowser unavailable", "info": info}
        row = archive_payload(db, trade_date=trade_date, exchange=exchange, kind=f"{kind}_browser_probe", source=source_name, payload=payload, rows=0, error=payload["error"])
        return {"ok": False, "archive_id": row.id, "source_file": row.path, "error": payload["error"], "info": info}

    code = """
import json, sys
from cloakbrowser import launch
url = sys.argv[1]
headless = sys.argv[2].lower() == 'true'
browser = launch(headless=headless)
try:
    page = browser.new_page()
    response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
    title = page.title()
    html = page.content()
    print(json.dumps({
        'ok': True,
        'url': page.url,
        'requested_url': url,
        'status': response.status if response else None,
        'title': title,
        'html': html[:200000],
        'html_length': len(html),
        'webdriver': page.evaluate('navigator.webdriver'),
        'user_agent': page.evaluate('navigator.userAgent'),
    }))
finally:
    browser.close()
"""
    try:
        proc = subprocess.run([rt.python_path, "-c", code, target, "true" if rt.headless else "false"], text=True, capture_output=True, timeout=rt.timeout_seconds, check=False)
        payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {"ok": False, "error": "empty browser output"}
        if proc.returncode != 0:
            payload.setdefault("ok", False)
            payload["error"] = payload.get("error") or proc.stderr.strip()[-1000:] or f"browser exited {proc.returncode}"
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "url": target, "error": f"{type(exc).__name__}: {exc}"}
    payload.update({"trade_date": trade_date, "exchange": exchange, "kind": kind, "source": source_name})
    row = archive_payload(
        db,
        trade_date=trade_date,
        exchange=exchange,
        kind=f"{kind}_browser_probe",
        source=source_name,
        payload=payload,
        rows=1 if payload.get("ok") else 0,
        error="" if payload.get("ok") else str(payload.get("error") or "browser probe failed"),
        content_type="application/json+browser-probe",
    )
    return {"ok": bool(payload.get("ok")), "archive_id": row.id, "source_file": row.path, "status": payload.get("status"), "title": payload.get("title"), "error": payload.get("error", ""), "info": info}
