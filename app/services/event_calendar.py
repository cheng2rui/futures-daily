from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings


@dataclass(frozen=True)
class CalendarEvent:
    date: str
    title: str
    category: str
    source: str
    summary: str
    importance: str = "normal"
    impact: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "title": self.title,
            "category": self.category,
            "source": self.source,
            "summary": self.summary,
            "importance": self.importance,
            "impact": self.impact,
            "note": self.note,
        }


MONTHLY_RULES = [
    {
        "key": "cn_cpi_pmi_window",
        "title": "中国宏观数据窗口",
        "category": "宏观数据",
        "source": "rule",
        "summary": "通常在月中至月末集中发布 CPI、PPI、社融、信贷、PMI 等宏观指标，影响黑色、能化、有色和金融期货的风险偏好。",
        "importance": "high",
        "impact": "关注商品价格和权益风险偏好的联动变化。",
        "day": 10,
    },
    {
        "key": "usda_wasde_window",
        "title": "USDA WASDE / 农产品报告窗口",
        "category": "农产品资讯",
        "source": "rule",
        "summary": "月度 USDA 供需报告通常在月中发布，容易影响油脂油料、软商品和谷物链条。",
        "importance": "high",
        "impact": "重点看油脂油料、软商品与美豆/美玉米外盘联动。",
        "day": 12,
    },
]


def _parse_trade_date(trade_date: str) -> date:
    return datetime.strptime(trade_date, "%Y%m%d").date()


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _last_day_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _next_weekday(d: date, weekday: int) -> date:
    offset = (weekday - d.weekday() + 7) % 7
    if offset == 0:
        offset = 7
    return d + timedelta(days=offset)


def _second_thursday(d: date) -> date:
    first = date(d.year, d.month, 1)
    offset = (3 - first.weekday() + 7) % 7  # Thursday
    first_thursday = first + timedelta(days=offset)
    return first_thursday + timedelta(days=7)


def _manual_event_file() -> Path:
    return Path("config/event_calendar.json")


def _load_manual_events() -> list[dict[str, Any]]:
    path = _manual_event_file()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        raw = raw.get("items") or []
    if not isinstance(raw, list):
        return []
    events: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            events.append(item)
    return events


def _normalize_manual_item(item: dict[str, Any]) -> CalendarEvent | None:
    dt = str(item.get("date") or "").strip()
    title = str(item.get("title") or item.get("name") or "").strip()
    if not dt or not title:
        return None
    return CalendarEvent(
        date=dt,
        title=title,
        category=str(item.get("category") or "手动事件"),
        source=str(item.get("source") or "manual"),
        summary=str(item.get("summary") or item.get("description") or ""),
        importance=str(item.get("importance") or "normal"),
        impact=str(item.get("impact") or ""),
        note=str(item.get("note") or ""),
    )


def build_event_calendar(trade_date: str, window_days: int = 14) -> dict[str, Any]:
    today = _parse_trade_date(trade_date)
    end = today + timedelta(days=max(1, window_days))
    items: list[CalendarEvent] = []

    # Near-term recurring global events.
    next_wed = _next_weekday(today - timedelta(days=1), 2)
    while next_wed <= end:
        items.append(CalendarEvent(
            date=_fmt(next_wed),
            title="美国 EIA 原油库存",
            category="能源/宏观",
            source="rule",
            summary="每周 EIA 库存数据，通常会影响 SC、LU、FU、RU 等能化链条和风险偏好。",
            importance="high",
            impact="关注原油、成品油、能化和化工链条的联动。",
        ))
        next_wed += timedelta(days=7)

    next_fri = _next_weekday(today - timedelta(days=1), 4)
    while next_fri <= end:
        items.append(CalendarEvent(
            date=_fmt(next_fri),
            title="CFTC 持仓报告 (COT)",
            category="资金/仓位",
            source="rule",
            summary="周度持仓披露，适合观察商品与金融期货的资金方向和拥挤度变化。",
            importance="normal",
            impact="重点看趋势品种的持仓分布是否恶化或改善。",
        ))
        next_fri += timedelta(days=7)

    second_thu = _second_thursday(today)
    if today <= second_thu <= end:
        items.append(CalendarEvent(
            date=_fmt(second_thu),
            title="USDA WASDE",
            category="农产品资讯",
            source="rule",
            summary="月度供需报告，常影响油脂油料、粕类、谷物和相关替代品种。",
            importance="high",
            impact="重点观察豆油、豆粕、菜油、棉花等链条。",
        ))

    month_end = _last_day_of_month(today)
    if today <= month_end <= end:
        items.append(CalendarEvent(
            date=_fmt(month_end),
            title="月末换月 / 保证金窗口",
            category="交易所公告",
            source="rule",
            summary="临近月末时，交易所保证金、限仓、换月和交割关注度通常上升。",
            importance="high",
            impact="留意近月合约流动性、换月节奏和风险控制。",
        ))

    for rule in MONTHLY_RULES:
        try:
            event_date = date(today.year, today.month, int(rule["day"]))
        except ValueError:
            continue
        if today <= event_date <= end:
            items.append(CalendarEvent(
                date=_fmt(event_date),
                title=str(rule["title"]),
                category=str(rule["category"]),
                source=str(rule["source"]),
                summary=str(rule["summary"]),
                importance=str(rule.get("importance") or "normal"),
                impact=str(rule.get("impact") or ""),
            ))

    for item in _load_manual_events():
        normalized = _normalize_manual_item(item)
        if not normalized:
            continue
        try:
            event_date = datetime.strptime(normalized.date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= event_date <= end:
            items.append(normalized)

    items.sort(key=lambda x: (x.date, x.importance != "high", x.title))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item.date, []).append(item.as_dict())

    high_count = sum(1 for item in items if item.importance == "high")
    return {
        "trade_date": trade_date,
        "window_days": window_days,
        "summary": {
            "count": len(items),
            "high_count": high_count,
            "next_event": items[0].as_dict() if items else None,
            "positioning": "本地事件日历：把宏观数据、USDA/EIA、月末换月和手动导入事件放到一张表里，方便日报查看。",
        },
        "items": [item.as_dict() for item in items],
        "by_date": grouped,
        "sources": [
            {"name": "rule", "status": "available", "note": "内置规则日历"},
            {"name": "manual", "status": "optional", "note": "config/event_calendar.json 手动导入"},
        ],
    }
