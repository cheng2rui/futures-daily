from __future__ import annotations

from app.services.dce_browser_parser import infer_column_mapping, parse_dce_table_candidate, parse_dce_candidates


def check() -> None:
    headers = ["名次", "会员简称", "成交量", "成交量增减", "持买单量", "持买单量增减", "持卖单量", "持卖单量增减"]
    mapping = infer_column_mapping(headers)
    assert mapping["rank"] == 0
    assert mapping["party"] == 1
    assert mapping["vol"] == 2
    assert mapping["long_open_interest"] == 4
    assert mapping["short_open_interest"] == 6

    candidate = {
        "headers": headers,
        "sample_rows": [
            headers,
            ["1", "永安期货", "1000", "10", "800", "20", "700", "-5"],
            ["2", "中信期货", "900", "-1", "600", "5", "650", "8"],
        ],
    }
    result = parse_dce_table_candidate(candidate)
    assert result["status"] == "ok"
    assert result["parsed_rows"] == 2
    assert result["sample"][0]["vol_party_name"] == "永安期货"
    assert result["sample"][0]["long_open_interest"] == 800
    assert result["sample"][1]["short_open_interest_chg"] == 8

    analysis = {"parser_plan": [{"type": "html_table", "confidence": "high", **candidate}]}
    parsed = parse_dce_candidates(analysis)
    assert parsed["status"] == "ok"
    assert parsed["tables_attempted"] == 1
    assert parsed["parsed_rows"] == 2


if __name__ == "__main__":
    check()
    print("ok")
