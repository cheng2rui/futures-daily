from __future__ import annotations

from app.services.browser_probe_analysis import analyze_browser_probe_candidates


def check() -> None:
    candidates = {
        "tables": [{
            "index": 0,
            "headers": ["名次", "会员简称", "成交量", "持买单量", "持卖单量"],
            "row_count_estimate": 21,
            "contains_position_keywords": True,
            "sample_rows": [["名次", "会员简称", "持买单量"], ["1", "永安期货", "100"]],
            "text_preview": "会员持仓排名 成交 持买 持卖 永安期货",
        }],
        "excel_links": [{"href": "rank.xlsx", "absolute_url": "https://www.dce.com.cn/rank.xlsx", "label": "会员持仓排名 Excel"}],
        "keyword_blocks": [{"keyword": "持仓", "text": "大连商品交易所 会员持仓排名 成交 持仓 排名"}],
    }
    result = analyze_browser_probe_candidates("DCE", candidates)
    assert result["status"] == "candidate_found"
    assert result["confidence"] == "high"
    assert result["best_candidate"]["type"] == "html_table"
    assert result["best_candidate"]["next_action"] == "write_dce_html_table_parser"
    assert any(item["type"] == "download_link" for item in result["parser_plan"])

    unsupported = analyze_browser_probe_candidates("INE", candidates)
    assert unsupported["status"] == "unsupported_exchange"


if __name__ == "__main__":
    check()
    print("ok")
