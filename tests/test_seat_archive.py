from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services import seat_archive


def _settings(root: Path, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(seat_archive=SimpleNamespace(enabled=enabled, path=str(root)))


def check() -> None:
    root = Path("tmp/test-seat-archive")
    trade_date = "20260525"
    day = root / trade_date
    day.mkdir(parents=True, exist_ok=True)
    (day / "index.json").write_text(json.dumps({"generatedAt": "now", "varieties": [{"file": "varieties/rb.json"}, {"file": "missing.json"}]}, ensure_ascii=False), encoding="utf-8")
    (day / "varieties").mkdir(parents=True, exist_ok=True)
    (day / "varieties" / "rb.json").write_text(json.dumps({
        "name": "RB",
        "displayName": "螺纹钢",
        "exchange": "SHFE",
        "netDelta": 12,
        "longShortRatio": 1.2,
        "longRows": [None, {"rank": 1, "member": "永安期货", "vol": 100, "delta": 20}],
        "shortRows": ["bad", {"rank": 1, "member": "乾坤期货", "vol": 40, "delta": -3}],
    }, ensure_ascii=False), encoding="utf-8")

    original_get_settings = seat_archive.get_settings
    try:
        seat_archive.get_settings = lambda: _settings(root)  # type: ignore[assignment]
        summary = seat_archive.load_archive_summary(trade_date)
        assert summary["status"] == "ok"
        assert summary["count"] == 1
        assert summary["skipped_files"] == 1
        assert summary["focus5"]["combined_by_variety"][0]["variety"] == "螺纹钢"

        bad_day = root / "20260526"
        bad_day.mkdir(parents=True, exist_ok=True)
        (bad_day / "index.json").write_text("{bad json", encoding="utf-8")
        bad_summary = seat_archive.load_archive_summary("20260526")
        assert bad_summary["status"] == "empty"
        assert "archive index unreadable" in bad_summary["reason"]
    finally:
        seat_archive.get_settings = original_get_settings  # type: ignore[assignment]


if __name__ == "__main__":
    check()
    print("ok")
