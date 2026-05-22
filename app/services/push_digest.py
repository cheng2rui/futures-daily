from __future__ import annotations

from typing import Any


def build_push_digest(report: dict[str, Any], max_abnormal: int = 5, max_watch: int = 6, max_viewpoints: int = 5) -> dict[str, Any]:
    """Build compact multi-channel digest text from a report payload.

    The output is plain text by design: safe for Telegram, WeChatBot, WeCom,
    logs, and copy/paste. It avoids markdown tables and keeps claims grounded in
    the existing report payload.
    """
    date = format_date(report.get("date"))
    overview = report.get("overview") or {}
    market = report.get("market") or {}
    intelligence = report.get("intelligence") or {}
    abnormal = intelligence.get("abnormal_cards") or []
    watch = (intelligence.get("watch_digest") or {}).get("items") or []
    watch_summary = (intelligence.get("watch_digest") or {}).get("summary") or ""
    viewpoints = (intelligence.get("news_digest") or {}).get("viewpoints") or []
    tomorrow = intelligence.get("tomorrow_watch") or []
    quality = report.get("data_quality") or {}
    risk_flags = report.get("risk_flags") or []

    lines = [
        f"【期货日报 {date or '-'}】",
        f"市场：{overview.get('stage', '-')}｜综合分 {overview.get('score', '-')}｜上涨/下跌 {market.get('up_count', 0)}/{market.get('down_count', 0)}",
    ]
    if overview.get("summary"):
        lines.append(shorten(overview["summary"], 120))

    lines.append("")
    lines.append("重点异动：")
    if abnormal:
        for idx, item in enumerate(abnormal[:max_abnormal], 1):
            name = item.get("name") or item.get("symbol")
            reason = "；".join((item.get("reasons") or [])[:3]) or item.get("signal") or "待确认"
            lines.append(f"{idx}. {name}｜{item.get('signal', '-')}｜{reason}")
    else:
        lines.append("- 暂无显著异动卡片")

    lines.append("")
    lines.append("我的关注：")
    if watch_summary:
        lines.append(shorten(watch_summary, 120))
    ok_watch = [x for x in watch if x.get("status") == "ok"]
    if ok_watch:
        for item in ok_watch[:max_watch]:
            chg = signed_pct(item.get("change_pct")) if item.get("change_pct") is not None else "-"
            vp = item.get("news_viewpoint") or {}
            vp_text = f"｜资讯{bias_label(vp.get('bias'))}" if vp else ""
            lines.append(f"- {item.get('name') or item.get('symbol')} {chg}｜{shorten(item.get('signal') or '-', 34)}{vp_text}")
    else:
        lines.append("- 暂无自选品种有效数据")

    lines.append("")
    lines.append("资讯观点：")
    if viewpoints:
        for item in viewpoints[:max_viewpoints]:
            lines.append(f"- {item.get('name') or item.get('symbol')}：{bias_label(item.get('bias'))}｜{shorten(item.get('summary'), 72)}")
    else:
        lines.append("- 暂无资讯观点摘要")

    lines.append("")
    lines.append("明日观察：")
    if tomorrow:
        for item in tomorrow[:5]:
            prefix = "!" if item.get("priority") == "high" else "-"
            lines.append(f"{prefix} {item.get('title')}：{shorten(item.get('body'), 70)}")
    else:
        lines.append("- 暂无观察项")

    if risk_flags or quality:
        lines.append("")
        coverage = quality.get("coverage_pct")
        q_text = f"数据覆盖：{coverage}%" if coverage is not None else "数据覆盖：未知"
        if risk_flags:
            q_text += "｜" + "；".join(risk_flags[:2])
        lines.append(q_text)
    lines.append("注：日报用于复盘和观察清单，不构成交易建议。")

    full_text = "\n".join(lines).strip()
    brief_lines = lines[:]
    # Compact brief for notification preview.
    while len("\n".join(brief_lines)) > 1200 and len(brief_lines) > 12:
        brief_lines.pop(-3 if len(brief_lines) > 3 else -1)
    return {"title": f"期货日报 {date or ''}".strip(), "text": full_text, "brief": "\n".join(brief_lines).strip()}


def format_date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def shorten(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，。；、 ") + "…"


def signed_pct(value: Any) -> str:
    try:
        n = float(value)
        return f"{n:+.2f}%"
    except Exception:
        return str(value or "-")


def bias_label(value: Any) -> str:
    return {"positive": "偏多", "negative": "偏空", "mixed": "分歧", "neutral": "中性"}.get(str(value or ""), "中性")
