from __future__ import annotations

from types import SimpleNamespace

from app.api.markets import _change_pct
from app.api.reports import _safe_schema_version


def check() -> None:
    assert _safe_schema_version({"report_schema_version": 5}) == 5
    assert _safe_schema_version({"report_schema_version": "5"}) == 5
    assert _safe_schema_version({"report_schema_version": "bad"}) == 0
    assert _safe_schema_version(None) == 0

    assert _change_pct(SimpleNamespace(close=110, pre_close=100, settlement=None, open=None)) == 10.0
    assert _change_pct(SimpleNamespace(close="bad", pre_close=100, settlement=None, open=None)) is None
    assert _change_pct(SimpleNamespace(close=100, pre_close=0, settlement=0, open=0)) is None


if __name__ == "__main__":
    check()
    print("ok")
