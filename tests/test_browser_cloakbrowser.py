from __future__ import annotations

import sys
from pathlib import Path

from app.services.browser.cloakbrowser import CloakBrowserRuntime, cloakbrowser_info


def check() -> None:
    missing = CloakBrowserRuntime(
        enabled=True,
        python_path="/definitely/missing/python",
        binary_path="/definitely/missing/chromium",
        headless=True,
        timeout_seconds=5,
    )
    unavailable = cloakbrowser_info(missing)
    assert unavailable["available"] is False
    assert unavailable["python_exists"] is False
    assert "not found" in unavailable["reason"]

    current = CloakBrowserRuntime(
        enabled=True,
        python_path=sys.executable,
        binary_path="",
        headless=True,
        timeout_seconds=10,
    )
    info = cloakbrowser_info(current)
    assert info["provider"] == "cloakbrowser"
    assert info["enabled"] is True
    assert info["python_exists"] is True
    # The app runtime may not have cloakbrowser installed; this probe must report
    # that cleanly instead of raising. Local v0.5.13 smoke is done with the
    # configured external venv.
    assert "available" in info

    configured_python = Path("/Users/rey/.openclaw/workspace/.venvs/cloakbrowser/bin/python")
    if configured_python.exists():
        configured = CloakBrowserRuntime(
            enabled=True,
            python_path=str(configured_python),
            binary_path="/Users/rey/.cloakbrowser/chromium-145.0.7632.109.2/Chromium.app/Contents/MacOS/Chromium",
            headless=True,
            timeout_seconds=20,
        )
        configured_info = cloakbrowser_info(configured)
        assert configured_info["available"] is True
        assert configured_info["probe"]["ok"] is True


if __name__ == "__main__":
    check()
    print("ok")
