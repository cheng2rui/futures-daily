from __future__ import annotations

import math
from types import SimpleNamespace

from app.services.structure import pct_change
from app.services.data_mart import safe_float_value, notional


def check() -> None:
    # pct_change edge cases
    assert pct_change(SimpleNamespace(pre_close=100, settlement=None, close=110)) == 10.0
    assert pct_change(SimpleNamespace(pre_close=100, settlement=105, close=110)) is not None
    assert pct_change(SimpleNamespace(pre_close=100, settlement=105, close=110)) == 10.0  # pre_close wins
    assert pct_change(SimpleNamespace(pre_close=None, settlement=105, close=110)) is not None
    chg_settlement = pct_change(SimpleNamespace(pre_close=None, settlement=105, close=110))
    assert abs(chg_settlement - 4.7619) < 0.01, f"got {chg_settlement}"
    assert pct_change(SimpleNamespace(pre_close=0, settlement=None, close=110)) is None
    assert pct_change(SimpleNamespace(pre_close="bad", settlement=None, close=110)) is None
    assert pct_change(SimpleNamespace(pre_close=None, settlement=None, close=110)) is None
    assert pct_change(SimpleNamespace(pre_close=100, settlement=None, close="bad")) is None

    # notional edge cases
    assert notional(SimpleNamespace(close=100, open_interest=1000), 10.0) == 1_000_000.0
    assert notional(SimpleNamespace(close=0, open_interest=1000), 10.0) is None
    assert notional(SimpleNamespace(close=100, open_interest=0), 10.0) is None
    assert notional(SimpleNamespace(close=100, open_interest=1000), None) is None
    assert notional(SimpleNamespace(close="bad", open_interest=1000), 10.0) is None

    # safe_float_value
    assert safe_float_value(42) == 42.0
    assert safe_float_value(0) == 0.0
    assert safe_float_value(None) == 0.0
    assert safe_float_value("") == 0.0
    assert safe_float_value("bad") == 0.0
    assert safe_float_value(float("nan")) == 0.0
    assert safe_float_value(math.inf) == math.inf


if __name__ == "__main__":
    check()
    print("ok")