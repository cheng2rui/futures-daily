from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Report
from app.services.assistant.service import analyze_seats, assistant_status, summarize_report
from app.services.trading_day import normalize_trade_date

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AskDailyIn(BaseModel):
    question: str = ""
    trade_date: str | None = None


@router.get("/status")
def status():
    return assistant_status()


@router.post("/summarize-report")
async def summarize(trade_date: str | None = None, db: Session = Depends(get_db)):
    report = _load_report(db, trade_date)
    result = await summarize_report(report)
    return result.__dict__


@router.post("/analyze-seat")
async def seat_analysis(trade_date: str | None = None, db: Session = Depends(get_db)):
    report = _load_report(db, trade_date)
    result = await analyze_seats(report)
    return result.__dict__


@router.post("/ask")
def ask_daily(payload: AskDailyIn, db: Session = Depends(get_db)):
    report = _load_report(db, payload.trade_date)
    return answer_daily_question(report, payload.question)


def _load_report(db: Session, trade_date: str | None) -> dict:
    if trade_date:
        td = normalize_trade_date(trade_date)
        row = db.scalar(select(Report).where(Report.trade_date == td))
    else:
        row = db.scalar(select(Report).order_by(desc(Report.trade_date)).limit(1))
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    return json.loads(row.report_json or "{}")


def answer_daily_question(report: dict[str, Any], question: str) -> dict[str, Any]:
    q = (question or "").strip()
    q_lower = q.lower()
    if not q:
        q_lower = "summary"

    if any(word in q_lower for word in ["历史", "极端", "分位", "罕见", "异常度", "percentile"]):
        return _history_answer(report, q)
    if any(word in q_lower for word in ["自选", "关注", "watch"]):
        return _watch_answer(report, q)
    if any(word in q_lower for word in ["明天", "观察", "next", "tomorrow"]):
        return _tomorrow_answer(report, q)
    if any(word in q_lower for word in ["数据", "缺", "完整", "质量", "够不够", "覆盖"]):
        return _quality_answer(report, q)
    if any(word in q_lower for word in ["席位", "多头", "空头", "持仓", "seat"]):
        return _seat_answer(report, q)
    if any(word in q_lower for word in ["异常", "异动", "最值得", "重点", "为什么", "原因"]):
        return _abnormal_answer(report, q)
    return _summary_answer(report, q)


def _summary_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    overview = report.get("overview") or {}
    market = report.get("market") or {}
    bullets = [
        overview.get("summary") or "暂无市场概览。",
        f"上涨 {market.get('up_count', 0)} 个，下跌 {market.get('down_count', 0)} 个，主力/活跃合约 {market.get('main_contracts') or market.get('liquid_contracts') or market.get('contracts') or 0} 个。",
    ]
    focus = _top_abnormal(report, limit=2)
    if focus:
        bullets.append("重点品种：" + "；".join(_name_signal(x) for x in focus))
    return _answer("今天整体怎么看？", overview.get("stage") or "暂无判断", bullets, question)


def _abnormal_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    items = _top_abnormal(report, limit=5)
    if not items:
        return _answer("今天哪些品种最异常？", "暂时没有特别突出的异动。", ["可以先看涨跌排行、成交最活跃和自选品种。"], question)
    bullets = []
    for item in items:
        evidence = item.get("evidence_chain") or []
        ev_text = "；".join(str(x.get("text") or "") for x in evidence[:2] if x.get("text"))
        line = _name_signal(item)
        hist = _history_summary(item)
        if hist:
            line += f"｜历史位置：{hist}"
        if ev_text:
            line += f"｜证据：{ev_text}"
        if item.get("watch_next"):
            line += f"｜明天看：{item.get('watch_next')}"
        bullets.append(line)
    return _answer("今天哪些品种最值得关注？", f"优先看 {items[0].get('name') or items[0].get('symbol')}。", bullets, question)


def _history_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    items = _top_abnormal(report, limit=6)
    bullets = []
    for item in items:
        hist = item.get("history_context") or {}
        name = item.get("name") or item.get("symbol") or "品种"
        if hist.get("status") != "ok":
            bullets.append(f"{name}：本地历史样本不足，暂不判断极端程度。")
            continue
        highlights = hist.get("highlights") or []
        text = "；".join(f"{x.get('label')}近{x.get('window')}日分位{x.get('percentile')}%" for x in highlights[:3])
        bullets.append(f"{name}：{text or hist.get('summary') or '历史位置暂不突出'}")
    if not bullets:
        bullets = ["当前日报还没有历史分位数据，建议先积累或补采更多历史行情。"]
    return _answer("这些异动历史上极端吗？", bullets[0], bullets, question)


def _watch_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    digest = ((report.get("intelligence") or {}).get("watch_digest") or {})
    items = digest.get("items") or report.get("watch_symbols") or []
    if not items:
        return _answer("我的自选品种怎么样？", "暂无自选品种数据。", ["可以先到设置里添加 TA2609、RU2609、RB 等关注项。"], question)
    bullets = []
    for item in items[:6]:
        name = item.get("name") or item.get("symbol") or "自选品种"
        signal = item.get("signal") or item.get("summary") or _change_text(item)
        line = f"{name}：{signal}"
        if item.get("watch_next"):
            line += f"｜明天看：{item.get('watch_next')}"
        bullets.append(line)
    return _answer("我的自选品种怎么样？", digest.get("summary") or f"共看到 {len(items)} 个自选品种。", bullets, question)


def _tomorrow_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    items = ((report.get("intelligence") or {}).get("tomorrow_watch") or [])
    if items:
        bullets = []
        for x in items[:8]:
            prefix = f"{x.get('category')}｜" if x.get("category") else ""
            line = f"{prefix}{x.get('title') or '观察项'}：{x.get('body') or ''}"
            if x.get("impact"):
                line += f"｜影响：{x.get('impact')}"
            bullets.append(line)
        return _answer("明天重点看什么？", items[0].get("title") or "先看重点观察清单。", bullets, question)
    abnormal = _top_abnormal(report, limit=5)
    bullets = [f"{x.get('name') or x.get('symbol')}：{x.get('watch_next')}" for x in abnormal if x.get("watch_next")]
    if not bullets:
        bullets = ["暂无明确观察项，可以先看自选品种、成交最活跃品种和席位变化。"]
    return _answer("明天重点看什么？", "优先看今天已有异动的品种是否延续。", bullets[:6], question)


def _quality_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    q = report.get("data_quality") or {}
    pct = q.get("overall_coverage_pct") if q.get("overall_coverage_pct") is not None else q.get("coverage_pct")
    rows = q.get("exchanges") or []
    bad = [x for x in rows if x.get("status") != "ok"]
    if not q or q.get("status") == "empty":
        return _answer("数据够不够用？", "暂无数据检查结果。", ["生成日报后会显示各交易所数据是否齐全。"], question)
    bullets = [q.get("summary") or f"数据完整度 {pct}%。"]
    for x in bad[:6]:
        bullets.append(f"{x.get('exchange')}：{x.get('note') or '部分数据缺失'}")
    if not bad:
        bullets.append("主要交易所数据已覆盖，日报解读可以正常参考。")
    return _answer("数据够不够用？", "数据够用。" if not bad else "有部分缺失，解读时需要留意。", bullets, question)


def _seat_answer(report: dict[str, Any], question: str) -> dict[str, Any]:
    seats = report.get("seats") or {}
    archive = seats.get("archive") or {}
    net_top = archive.get("net_delta_top") or []
    long_top = seats.get("long_increase_top") or []
    short_top = seats.get("short_increase_top") or []
    bullets = []
    for x in net_top[:4]:
        bullets.append(f"{x.get('displayName') or x.get('name') or x.get('variety')}：净变化 {x.get('netDelta', '-')}，方向 {x.get('netDir') or '-'}。")
    if long_top:
        x = long_top[0]
        bullets.append(f"多头加仓靠前：{x.get('variety')} / {x.get('seat')}，变化 {x.get('change', '-')}。")
    if short_top:
        x = short_top[0]
        bullets.append(f"空头加仓靠前：{x.get('variety')} / {x.get('seat')}，变化 {x.get('change', '-')}。")
    if not bullets:
        bullets.append("暂无明显席位变化，可能是席位数据缺失或该日变化不突出。")
    return _answer("席位有什么变化？", bullets[0], bullets, question)


def _top_abnormal(report: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    return list(((report.get("intelligence") or {}).get("abnormal_cards") or [])[:limit])


def _name_signal(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("symbol") or "品种"
    signal = item.get("signal") or item.get("summary") or _change_text(item) or "有变化"
    return f"{name}：{signal}"


def _change_text(item: dict[str, Any]) -> str:
    change = item.get("change_pct")
    close = item.get("close")
    parts = []
    if change is not None:
        parts.append(f"涨跌幅 {change}%")
    if close is not None:
        parts.append(f"收盘 {close}")
    return "，".join(parts) or "暂无明显结论"


def _history_summary(item: dict[str, Any]) -> str:
    hist = item.get("history_context") or {}
    if hist.get("status") != "ok":
        return ""
    highlights = hist.get("highlights") or []
    if not highlights:
        return hist.get("summary") or ""
    return "；".join(f"{x.get('label')}近{x.get('window')}日分位{x.get('percentile')}%" for x in highlights[:2])


def _answer(title: str, headline: str, bullets: list[str], question: str) -> dict[str, Any]:
    clean_bullets = [str(x).strip() for x in bullets if str(x or "").strip()]
    return {
        "question": question,
        "title": title,
        "headline": headline,
        "bullets": clean_bullets[:8],
    }
