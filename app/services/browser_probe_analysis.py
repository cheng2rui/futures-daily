from __future__ import annotations

from typing import Any

SEAT_HEADER_KEYWORDS = ["会员", "名次", "排名", "成交", "持买", "持卖", "多头", "空头", "增减", "持仓"]
DCE_HINT_KEYWORDS = ["大连商品交易所", "大商所", "DCE", "会员持仓", "持仓排名", "成交持仓排名"]


def analyze_browser_probe_candidates(exchange: str, candidates: dict[str, Any]) -> dict[str, Any]:
    exchange = str(exchange or "").upper()
    if exchange == "DCE":
        return analyze_dce_candidates(candidates)
    return {
        "exchange": exchange,
        "status": "unsupported_exchange",
        "confidence": "low",
        "message": f"browser probe candidate analyzer for {exchange} is not implemented yet",
        "parser_plan": [],
    }


def analyze_dce_candidates(candidates: dict[str, Any]) -> dict[str, Any]:
    tables = candidates.get("tables") or []
    links = candidates.get("excel_links") or []
    blocks = candidates.get("keyword_blocks") or []
    table_plans = [score_table_candidate(t) for t in tables]
    link_plans = [score_link_candidate(x) for x in links]
    block_plans = [score_block_candidate(b) for b in blocks]
    parser_plan = sorted(table_plans + link_plans + block_plans, key=lambda x: (-x["score"], x["type"], x.get("index", 999)))
    best = parser_plan[0] if parser_plan else None
    confidence = "high" if best and best["score"] >= 8 else "medium" if best and best["score"] >= 5 else "low"
    status = "candidate_found" if best else "no_candidate"
    return {
        "exchange": "DCE",
        "status": status,
        "confidence": confidence,
        "best_candidate": best,
        "parser_plan": parser_plan[:10],
        "counts": {"tables": len(tables), "excel_links": len(links), "keyword_blocks": len(blocks)},
        "message": dce_message(status, confidence, best),
    }


def score_table_candidate(table: dict[str, Any]) -> dict[str, Any]:
    headers = [str(x) for x in table.get("headers") or []]
    preview = str(table.get("text_preview") or "")
    haystack = " ".join(headers) + " " + preview
    matched = [kw for kw in SEAT_HEADER_KEYWORDS if kw in haystack]
    score = len(set(matched)) * 2
    if table.get("contains_position_keywords"):
        score += 2
    if int(table.get("row_count_estimate") or 0) >= 5:
        score += 1
    if any("会员" in h for h in headers):
        score += 2
    if any("持买" in h or "持卖" in h for h in headers):
        score += 2
    return {
        "type": "html_table",
        "index": table.get("index", 0),
        "score": score,
        "confidence": confidence_from_score(score),
        "matched_keywords": sorted(set(matched)),
        "headers": headers[:20],
        "row_count_estimate": table.get("row_count_estimate", 0),
        "sample_rows": table.get("sample_rows", [])[:3],
        "next_action": "write_dce_html_table_parser" if score >= 6 else "inspect_table_manually",
    }


def score_link_candidate(link: dict[str, Any]) -> dict[str, Any]:
    label = str(link.get("label") or "")
    href = str(link.get("href") or "")
    haystack = f"{label} {href}"
    score = 0
    if any(ext in href.lower() for ext in [".xls", ".xlsx", ".csv"]):
        score += 4
    matched = [kw for kw in SEAT_HEADER_KEYWORDS + DCE_HINT_KEYWORDS if kw in haystack]
    score += len(set(matched)) * 2
    return {
        "type": "download_link",
        "score": score,
        "confidence": confidence_from_score(score),
        "matched_keywords": sorted(set(matched)),
        "label": label,
        "href": href,
        "absolute_url": link.get("absolute_url") or href,
        "next_action": "download_and_archive_file_then_parser_replay" if score >= 5 else "inspect_link_manually",
    }


def score_block_candidate(block: dict[str, Any]) -> dict[str, Any]:
    text = str(block.get("text") or "")
    matched = [kw for kw in SEAT_HEADER_KEYWORDS + DCE_HINT_KEYWORDS if kw in text]
    score = len(set(matched))
    if "会员" in text and "持仓" in text:
        score += 2
    return {
        "type": "keyword_block",
        "score": score,
        "confidence": confidence_from_score(score),
        "matched_keywords": sorted(set(matched)),
        "keyword": block.get("keyword"),
        "text": text[:500],
        "next_action": "inspect_nearby_dom_or_link" if score >= 3 else "low_priority_context",
    }


def confidence_from_score(score: int) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def dce_message(status: str, confidence: str, best: dict[str, Any] | None) -> str:
    if status != "candidate_found" or not best:
        return "未发现明显 DCE 席位 parser 候选；建议检查是否进入 challenge/首页或日期参数不对。"
    return f"发现 DCE 席位候选：{best.get('type')}，置信度 {confidence}，建议动作：{best.get('next_action')}。"
