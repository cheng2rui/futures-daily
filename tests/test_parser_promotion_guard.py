from __future__ import annotations

from app.services.parser_promotion_guard import evaluate_parser_promotion


def check() -> None:
    good = {
        "results": [{
            "input_rows": 10,
            "parsed_rows": 9,
            "error_count": 1,
            "mapping": {"rank": 0, "party": 1, "long_open_interest": 4},
        }]
    }
    ok = evaluate_parser_promotion(good)
    assert ok["allowed"] is True
    assert ok["status"] == "pass"
    assert ok["metrics"]["success_rate"] == 90.0

    few = {
        "results": [{
            "input_rows": 2,
            "parsed_rows": 2,
            "error_count": 0,
            "mapping": {"rank": 0, "party": 1, "long_open_interest": 4},
        }]
    }
    blocked = evaluate_parser_promotion(few)
    assert blocked["allowed"] is False
    assert any(r["code"] == "too_few_rows" for r in blocked["reasons"])

    bad_mapping = {"input_rows": 10, "parsed_rows": 10, "error_count": 0, "mapping": {"rank": 0}}
    blocked2 = evaluate_parser_promotion(bad_mapping)
    assert blocked2["allowed"] is False
    assert any(r["code"] == "missing_required_mapping" for r in blocked2["reasons"])

    missing = evaluate_parser_promotion(None)
    assert missing["allowed"] is False
    assert missing["reasons"][0]["code"] == "no_parser_dry_run"


if __name__ == "__main__":
    check()
    print("ok")
