from __future__ import annotations

from app.services.error_classifier import classify_error, summarize_categories


def check() -> None:
    anti = classify_error("DCE returned 412 challenge page", source="akshare", kind="daily")
    assert anti["code"] == "anti_bot"
    assert "反爬" in anti["label"]

    empty = classify_error("empty seat rank", kind="seat_rank")
    assert empty["code"] == "empty"

    parser = classify_error("KeyError: settlement column missing")
    assert parser["code"] == "parser"

    missing = classify_error("", status="failed")
    assert missing["code"] == "missing_without_error"

    summary = summarize_categories([anti, empty, empty])
    assert summary["top_code"] == "empty"
    assert summary["counts"]["empty"] == 2

    mixed = summarize_categories([classify_error("未采集"), empty])
    assert mixed["top_code"] == "empty"
    assert mixed["unknown_count"] == 1


if __name__ == "__main__":
    check()
    print("ok")
