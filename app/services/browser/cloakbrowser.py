from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings


@dataclass(frozen=True)
class CloakBrowserRuntime:
    enabled: bool
    python_path: str
    binary_path: str
    headless: bool
    timeout_seconds: int


def runtime_from_settings() -> CloakBrowserRuntime:
    cfg = get_settings().browser
    return CloakBrowserRuntime(
        enabled=bool(cfg.enabled),
        python_path=str(cfg.python_path),
        binary_path=str(cfg.binary_path),
        headless=bool(cfg.headless),
        timeout_seconds=max(5, int(cfg.timeout_seconds or 60)),
    )


def cloakbrowser_info(runtime: CloakBrowserRuntime | None = None) -> dict[str, Any]:
    """Return local CloakBrowser availability without launching a page.

    The project keeps CloakBrowser in an external venv so Docker/runtime installs
    do not need the stealth browser dependency unless an operator explicitly
    enables browser probes. This probe is intentionally read-only.
    """
    rt = runtime or runtime_from_settings()
    python = Path(rt.python_path)
    binary = Path(rt.binary_path) if rt.binary_path else None
    result: dict[str, Any] = {
        "provider": "cloakbrowser",
        "enabled": rt.enabled,
        "python_path": rt.python_path,
        "python_exists": python.exists(),
        "binary_path": rt.binary_path,
        "binary_exists": bool(binary and binary.exists()),
        "headless": rt.headless,
        "timeout_seconds": rt.timeout_seconds,
        "available": False,
    }
    if not rt.enabled:
        result["reason"] = "browser automation disabled"
        return result
    if not python.exists():
        result["reason"] = "cloakbrowser python venv not found"
        return result

    code = """
import json
try:
    import cloakbrowser
    from cloakbrowser.download import binary_info
    info = binary_info()
    print(json.dumps({"ok": True, "version": getattr(cloakbrowser, "__version__", None), "binary_info": info}, default=str))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
"""
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            text=True,
            capture_output=True,
            timeout=rt.timeout_seconds,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        result["reason"] = f"probe failed: {type(exc).__name__}: {exc}"
        return result

    result["returncode"] = proc.returncode
    if proc.stderr.strip():
        result["stderr"] = proc.stderr.strip()[-1000:]
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"ok": False, "error": proc.stdout.strip()[-1000:] or "empty probe output"}
    result["probe"] = payload
    result["available"] = bool(proc.returncode == 0 and payload.get("ok"))
    if not result["available"]:
        result["reason"] = payload.get("error") or "cloakbrowser import probe failed"
    return result


def run_cloakbrowser_smoke(url: str = "data:text/html,<title>FuturesDailyCloakSmoke</title><h1>ok</h1>", runtime: CloakBrowserRuntime | None = None) -> dict[str, Any]:
    """Launch CloakBrowser against a harmless data URL and report webdriver/UA.

    This is a local smoke test for the browser stack. Official exchange probes
    should call a separate source adapter that archives raw responses before any
    parser tries to normalize them.
    """
    rt = runtime or runtime_from_settings()
    info = cloakbrowser_info(rt)
    if not info.get("available"):
        return {"ok": False, "info": info}

    code = """
import json, sys
from cloakbrowser import launch
url = sys.argv[1]
headless = sys.argv[2].lower() == 'true'
browser = launch(headless=headless)
try:
    page = browser.new_page()
    page.goto(url)
    print(json.dumps({
        "ok": True,
        "title": page.title(),
        "webdriver": page.evaluate('navigator.webdriver'),
        "user_agent": page.evaluate('navigator.userAgent'),
    }))
finally:
    browser.close()
"""
    try:
        proc = subprocess.run(
            [rt.python_path, "-c", code, url, "true" if rt.headless else "false"],
            text=True,
            capture_output=True,
            timeout=rt.timeout_seconds,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "info": info, "error": f"{type(exc).__name__}: {exc}"}
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"ok": False, "error": proc.stdout.strip()[-1000:] or "empty smoke output"}
    return {
        "ok": bool(proc.returncode == 0 and payload.get("ok")),
        "info": info,
        "returncode": proc.returncode,
        "stderr": proc.stderr.strip()[-1000:] if proc.stderr.strip() else "",
        "result": payload,
    }
