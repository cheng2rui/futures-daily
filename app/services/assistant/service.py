from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import get_settings


@dataclass
class AssistantResult:
    enabled: bool
    feature: str
    text: str
    model: str | None = None
    skipped_reason: str | None = None


def assistant_status() -> dict[str, Any]:
    cfg = get_settings().assistant
    data = cfg.model_dump()
    if data.get("provider", {}).get("api_key"):
        data["provider"]["api_key"] = "***"
    return data


async def summarize_report(report: dict[str, Any]) -> AssistantResult:
    cfg = get_settings().assistant
    if not cfg.enabled or not cfg.features.daily_summary:
        return deterministic_daily_summary(report, skipped_reason="assistant daily_summary disabled")
    return deterministic_daily_summary(report, skipped_reason="LLM provider not wired yet")


async def analyze_seats(report: dict[str, Any]) -> AssistantResult:
    cfg = get_settings().assistant
    if not cfg.enabled or not cfg.features.seat_analysis:
        return deterministic_seat_summary(report, skipped_reason="assistant seat_analysis disabled")
    return deterministic_seat_summary(report, skipped_reason="LLM provider not wired yet")


def deterministic_daily_summary(report: dict[str, Any], skipped_reason: str | None = None) -> AssistantResult:
    overview = report.get("overview") or {}
    quality = report.get("data_quality") or {}
    sectors = report.get("sectors") or []
    top_sector = sectors[0]["name"] if sectors else "暂无"
    weak_sector = sectors[-1]["name"] if sectors else "暂无"
    flags = report.get("risk_flags") or []
    text = (
        f"市场状态：{overview.get('stage', '暂无')}，综合分 {overview.get('score', '-')}; "
        f"上涨 {report.get('market', {}).get('up_count', 0)} 个、下跌 {report.get('market', {}).get('down_count', 0)} 个。"
        f" 数据覆盖 {quality.get('coverage_pct', 0)}%，状态 {quality.get('status', '-')}; "
        f"强势板块：{top_sector}，弱势板块：{weak_sector}。"
    )
    if flags:
        text += " 风险提示：" + "；".join(flags)
    return AssistantResult(enabled=False, feature="daily_summary", text=text, skipped_reason=skipped_reason)


def deterministic_seat_summary(report: dict[str, Any], skipped_reason: str | None = None) -> AssistantResult:
    seats = report.get("seats") or {}
    long_top = seats.get("long_increase_top") or []
    short_top = seats.get("short_increase_top") or []
    watch = seats.get("watchlist") or []
    text = f"席位动向：增多榜 {len(long_top)} 条，增空榜 {len(short_top)} 条，关注席位命中 {len(watch)} 条。"
    if long_top:
        x = long_top[0]
        text += f" 增多最明显：{x.get('seat') or '-'} {x.get('variety')}/{x.get('contract')} +{x.get('change')}。"
    if short_top:
        x = short_top[0]
        text += f" 增空最明显：{x.get('seat') or '-'} {x.get('variety')}/{x.get('contract')} +{x.get('change')}。"
    return AssistantResult(enabled=False, feature="seat_analysis", text=text, skipped_reason=skipped_reason)
