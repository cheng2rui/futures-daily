from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.metadata.contract_specs import get_point_value
from app.metadata.variety_meta import get_exchange_code, get_variety_name
from app.models import CapitalFlowDaily, DailyBar, Report, SeatRankRow, WatchSymbol, SeatWatchlist
from app.services.data_mart import build_variety_dataset, materialize_variety_dataset
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_quality import build_data_quality
from app.services.event_calendar import build_event_calendar
from app.services.gap_analysis import build_gap_analysis
from app.services.history_factors import build_history_context
from app.services.industry_chain import build_industry_chain_digest
from app.services.news_collector import load_latest_news_digest
from app.services.push_digest import build_push_digest
from app.services.seat_archive import load_archive_summary
from app.services.structure import build_structure, pct_change, sector_for
from app.services.term_structure import build_term_structure


from app.version import VERSION

REPORT_SCHEMA_VERSION = 9
LIQUID_MIN_VOLUME = 1000
LIQUID_MIN_OPEN_INTEREST = 1000
PRICE_FLAT_THRESHOLD_PCT = 0.2


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pct_delta(delta: float | None, base: float | None) -> float | None:
    if delta is None or not base:
        return None
    return delta / base * 100


def temperature_stage(score: float) -> str:
    if score >= 85:
        return "极热"
    if score >= 70:
        return "高温"
    if score >= 55:
        return "偏热"
    if score >= 40:
        return "中性"
    if score >= 25:
        return "偏冷"
    return "冰点"


def market_temperature_tone(stage: str) -> str:
    if stage in {"极热", "高温"}:
        return "warning"
    if stage in {"偏热", "中性"}:
        return "neutral"
    return "info"


def direction_label(direction_bias: float, activity_score: float, oi_delta_pct: float | None) -> str:
    if activity_score < 35 and oi_delta_pct is not None and oi_delta_pct < -1:
        return "资金退潮"
    if abs(direction_bias) < 0.18:
        return "多空分歧"
    return "多方占优" if direction_bias > 0 else "空方占优"


def build_market_temperature(
    *,
    ranking_valid: list[tuple[DailyBar, float]],
    main_bars: list[DailyBar],
    main_oi_deltas: dict[tuple[str, str, str], float | None] | None = None,
    sectors: list[dict] | None = None,
    volume_delta_pct: float | None = None,
    capital_flow_amount: float = 0.0,
    capital_inflow_amount: float = 0.0,
    capital_outflow_amount: float = 0.0,
    total_oi_delta: float | None = None,
    total_oi: float | None = None,
) -> dict:
    """期货市场综合温度：衡量市场活跃度/资金博弈强度，方向单独表达多空归属。"""
    main_oi_deltas = main_oi_deltas or {}
    sectors = sectors or []
    valid_items = [(bar, chg) for bar, chg in ranking_valid if chg is not None]
    valid_count = max(1, len(valid_items))
    oi_delta_pct = _pct_delta(total_oi_delta, (total_oi or 0) - (total_oi_delta or 0))

    # 1) 资金流强度 25：资金流入/流出、全市场持仓变化、成交较前日变化共同决定活跃度。
    gross_flow = abs(capital_inflow_amount) + abs(capital_outflow_amount)
    flow_score = _clamp(gross_flow / 20_000_000_000 * 8, 0, 8) if gross_flow else 0
    flow_score += _clamp(abs(capital_flow_amount) / 10_000_000_000 * 4, 0, 4) if gross_flow else 0
    volume_score = 6.0 if volume_delta_pct is None else _clamp(6 + volume_delta_pct * 0.18, 0, 10)
    oi_flow_score = 5.0 if oi_delta_pct is None else _clamp(5 + oi_delta_pct * 0.9, 0, 10)
    capital_score = round(_clamp(flow_score + volume_score + oi_flow_score, 0, 25), 1)

    # 2) 多空占优强度 25：上涨增仓/下跌增仓都是高温，方向由多空偏置决定。
    long_points = 0.0
    short_points = 0.0
    directional_activity = 0.0
    for bar, chg in valid_items:
        key = (get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper(), str(bar.contract or ""))
        oi_delta = main_oi_deltas.get(key)
        oi_sign = 1 if oi_delta is not None and oi_delta > 0 else -1 if oi_delta is not None and oi_delta < 0 else 0
        abs_chg = abs(chg)
        if abs_chg < PRICE_FLAT_THRESHOLD_PCT:
            item_activity = 0.7 if oi_sign > 0 else 0.25 if oi_sign < 0 else 0.4
        elif chg > 0:
            item_activity = 1.0 if oi_sign > 0 else 0.65 if oi_sign < 0 else 0.75
            long_points += item_activity * (1 + min(abs_chg, 3) / 3)
        else:
            item_activity = 1.0 if oi_sign > 0 else 0.65 if oi_sign < 0 else 0.75
            short_points += item_activity * (1 + min(abs_chg, 3) / 3)
        directional_activity += item_activity
    dominance_score = round(_clamp(directional_activity / valid_count * 25, 0, 25), 1)

    # 3) 板块多空共振 20：板块涨跌方向越清晰、活跃板块越多，温度越高。
    sector_signal_count = 0
    sector_activity = 0.0
    for sector in sectors:
        count = max(1, int(sector.get("count") or 0))
        up = float(sector.get("up") or 0)
        down = float(sector.get("down") or 0)
        imbalance = abs(up - down) / count
        if count >= 2:
            sector_signal_count += 1
            sector_activity += _clamp(0.35 + imbalance * 0.9, 0, 1)
    sector_score = round(_clamp((sector_activity / max(1, sector_signal_count)) * 20, 0, 20), 1) if sector_signal_count else 8.0

    # 4) 主力合约日增减仓确认 20：主力价格方向明确且增仓，趋势确认度最高；减仓则打折。
    main_confirmation = 0.0
    main_count = 0
    for bar in main_bars:
        chg = pct_change(bar)
        if chg is None:
            continue
        key = (get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper(), str(bar.contract or ""))
        oi_delta = main_oi_deltas.get(key)
        if oi_delta is None:
            item = 10.0
        elif abs(chg) < PRICE_FLAT_THRESHOLD_PCT:
            item = 14.0 if oi_delta > 0 else 5.0 if oi_delta < 0 else 8.0
        elif oi_delta > 0:
            item = 20.0
        elif oi_delta < 0:
            item = 12.0
        else:
            item = 14.0
        main_confirmation += item
        main_count += 1
    main_score = round(_clamp(main_confirmation / max(1, main_count), 0, 20), 1) if main_count else 10.0

    # 5) 波动/成交活跃 10：只衡量交易机会/波动强度，不判断多空。
    avg_abs_change = sum(abs(chg) for _, chg in valid_items) / valid_count if valid_items else 0.0
    volatility_score = 3 + min(avg_abs_change * 2.4, 5)
    if volume_delta_pct is not None:
        volatility_score += _clamp(volume_delta_pct * 0.05, -2, 2)
    volatility_score = round(_clamp(volatility_score, 0, 10), 1)

    score = round(_clamp(capital_score + dominance_score + sector_score + main_score + volatility_score, 0, 100), 1)
    direction_denominator = max(1.0, long_points + short_points)
    bias = (long_points - short_points) / direction_denominator
    direction = direction_label(bias, score, oi_delta_pct)
    long_ratio = round(long_points / direction_denominator * 100, 1)
    short_ratio = round(short_points / direction_denominator * 100, 1)

    details = [
        {"name": "资金流强度", "score": capital_score, "max": 25, "note": "资金流、成交较前日、全市场持仓变化"},
        {"name": "多空占优强度", "score": dominance_score, "max": 25, "note": "价格涨跌 + 主力日增减仓四象限"},
        {"name": "板块多空共振", "score": sector_score, "max": 20, "note": "板块上涨/下跌扩散与方向一致性"},
        {"name": "主力合约确认", "score": main_score, "max": 20, "note": "主力合约上涨/下跌是否由增仓确认"},
        {"name": "波动成交活跃", "score": volatility_score, "max": 10, "note": "主力涨跌幅与成交变化"},
    ]
    return {
        "score": score,
        "stage": temperature_stage(score),
        "heat": f"{temperature_stage(score)}｜{direction}",
        "risk": round(100 - score, 1),
        "direction": direction,
        "direction_bias": round(bias, 3),
        "long_ratio": long_ratio,
        "short_ratio": short_ratio,
        "capital_flow_amount": round(capital_flow_amount, 2),
        "total_oi_delta": round(total_oi_delta, 2) if total_oi_delta is not None else None,
        "total_oi_delta_pct": round(oi_delta_pct, 2) if oi_delta_pct is not None else None,
        "volume_delta_pct": volume_delta_pct,
        "details": details,
    }


def notional_value(bar: DailyBar) -> float | None:
    pv = get_point_value(bar.symbol)
    if pv is None or bar.close is None or bar.open_interest is None:
        return None
    return round(bar.close * bar.open_interest * pv, 2)


def build_report(db: Session, trade_date: str) -> Report:
    bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date == trade_date)))
    main_bars = pick_main_bars(bars)
    changes = [(bar, pct_change(bar)) for bar in main_bars]
    valid = [(bar, chg) for bar, chg in changes if chg is not None]
    liquid_valid = [(bar, chg) for bar, chg in valid if is_liquid_bar(bar)]
    ranking_valid = liquid_valid or valid

    up_count = sum(1 for _, chg in ranking_valid if chg > 0)
    down_count = sum(1 for _, chg in ranking_valid if chg < 0)
    turnover = sum((bar.turnover or 0) for bar in bars)
    volume = sum((bar.volume or 0) for bar in bars)
    prev_volume = previous_total_volume(db, trade_date)
    volume_delta = volume - prev_volume if prev_volume is not None else None
    volume_delta_pct = round(volume_delta / prev_volume * 100, 1) if volume_delta is not None and prev_volume else None

    sector_bucket: dict[str, list[float]] = defaultdict(list)
    for bar, chg in ranking_valid:
        sector_bucket[sector_for(bar.symbol)].append(chg)
    sectors = [
        {"name": name, "avg_change": round(sum(vals) / len(vals), 2), "count": len(vals)}
        for name, vals in sector_bucket.items() if vals
    ]
    sectors.sort(key=lambda x: x["avg_change"], reverse=True)

    gainers = sorted(ranking_valid, key=lambda x: x[1], reverse=True)[:10]
    losers = sorted(ranking_valid, key=lambda x: x[1])[:10]
    volume_top = sorted(bars, key=lambda x: x.volume or 0, reverse=True)[:10]
    oi_top = sorted(bars, key=lambda x: x.open_interest or 0, reverse=True)[:10]

    seat_rows = list(db.scalars(select(SeatRankRow).where(SeatRankRow.trade_date == trade_date).limit(5000)))
    seat_long = sorted(
        [r for r in seat_rows if r.long_party_name and r.long_open_interest_chg is not None and (r.rank or 999) <= 20],
        key=lambda r: r.long_open_interest_chg or 0,
        reverse=True,
    )[:10]
    seat_short = sorted(
        [r for r in seat_rows if r.short_party_name and r.short_open_interest_chg is not None and (r.rank or 999) <= 20],
        key=lambda r: r.short_open_interest_chg or 0,
        reverse=True,
    )[:10]

    valid_count = max(1, up_count + down_count)

    def bar_item(bar: DailyBar, chg: float | None = None) -> dict:
        raw = {}
        try:
            raw = json.loads(bar.raw_json or "{}")
        except Exception:
            raw = {}
        return {
            "exchange": get_exchange_code(bar.symbol, bar.exchange),
            "symbol": bar.symbol,
            "name": get_variety_name(bar.symbol),
            "contract": bar.contract,
            "sector": sector_for(bar.symbol),
            "close": bar.close,
            "change_pct": round(chg, 2) if chg is not None else None,
            "volume": bar.volume,
            "open_interest": bar.open_interest,
            "turnover": bar.turnover,
            "notional_oi": notional_value(bar),
            "source": raw.get("_source") or raw.get("source") or "akshare",
        }

    data_quality = build_data_quality(db, trade_date)
    structure = build_structure(bars)
    term_structure = build_term_structure(bars)
    event_calendar = build_event_calendar(trade_date)
    seat_archive = load_archive_summary(trade_date)
    dataset = build_variety_dataset(db, trade_date)
    capital_flow_rows = list(db.scalars(select(CapitalFlowDaily).where(CapitalFlowDaily.trade_date == trade_date)))
    capital_flow_amount = sum(float(row.amount or 0) for row in capital_flow_rows)
    capital_inflow_amount = sum(float(row.amount or 0) for row in capital_flow_rows if (row.amount or 0) > 0)
    capital_outflow_amount = sum(float(row.amount or 0) for row in capital_flow_rows if (row.amount or 0) < 0)
    main_oi_deltas = previous_main_open_interest_deltas(db, trade_date, main_bars)
    total_oi_delta = previous_total_open_interest_delta(db, trade_date)
    total_oi = sum(float(bar.open_interest or 0) for bar in bars)
    temperature = build_market_temperature(
        ranking_valid=ranking_valid,
        main_bars=main_bars,
        main_oi_deltas=main_oi_deltas,
        sectors=structure.get("sector_breadth") or sectors,
        volume_delta_pct=volume_delta_pct,
        capital_flow_amount=capital_flow_amount,
        capital_inflow_amount=capital_inflow_amount,
        capital_outflow_amount=capital_outflow_amount,
        total_oi_delta=total_oi_delta,
        total_oi=total_oi,
    )
    score = temperature["score"]
    stage = temperature["stage"]
    heat = temperature["heat"]
    risk = temperature["risk"]
    materialize_variety_dataset(db, trade_date)
    coverage_matrix = build_coverage_matrix(db, trade_date, sync_gaps=True)
    data_quality["coverage_matrix"] = coverage_matrix
    gap_analysis = build_gap_analysis(db, trade_date)
    history_context = build_history_context(db, trade_date)
    watch_symbols = list(db.scalars(select(WatchSymbol).where(WatchSymbol.enabled == True)))  # noqa: E712
    watch_symbol_codes = {w.symbol.upper() for w in watch_symbols}
    watch_bars = [bar_item(b, pct_change(b)) for b in bars if b.symbol.upper() in watch_symbol_codes]
    watch_seats = list(db.scalars(select(SeatWatchlist).where(SeatWatchlist.enabled == True)))  # noqa: E712
    watch_seat_names = {s.seat_name for s in watch_seats}
    watch_seat_rows = [
        seat_watch_item(r)
        for r in seat_rows
        if r.long_party_name in watch_seat_names or r.short_party_name in watch_seat_names or r.vol_party_name in watch_seat_names
    ][:50]

    news_digest = load_latest_news_digest(db, trade_date)
    abnormal_cards = build_abnormal_cards(dataset, news_digest=news_digest, history_context=history_context)
    industry_chain = build_industry_chain_digest(dataset, abnormal_cards)
    watch_digest = build_watch_digest(dataset, watch_symbols, abnormal_cards, news_digest)
    tomorrow_watch = build_tomorrow_watch(abnormal_cards, data_quality, gap_analysis, news_digest)
    report_sections = build_report_sections(
        up_count=up_count,
        down_count=down_count,
        stage=stage,
        score=score,
        structure=structure,
        seat_archive=seat_archive,
        dataset=dataset,
        data_quality=data_quality,
        gap_analysis=gap_analysis,
        seat_long=seat_long,
        seat_short=seat_short,
        abnormal_cards=abnormal_cards,
    )
    report_brief = build_report_brief(report_sections, stage, score)

    payload = {
        "date": trade_date,
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": VERSION,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "product_positioning": "不做实时行情交易终端，只做盘后/阶段性资讯收集、数据拆解、异动归因和市场日报。",
        },
        "overview": {
            "score": score,
            "stage": stage,
            "heat": heat,
            "risk": risk,
            "direction": temperature.get("direction"),
            "temperature": temperature,
            "summary": report_sections[0]["body"],
        },
        "market": {
            "up_count": up_count,
            "down_count": down_count,
            "turnover": turnover,
            "volume": volume,
            "volume_prev": prev_volume,
            "volume_delta": volume_delta,
            "volume_delta_pct": volume_delta_pct,
            "capital_flow_amount": capital_flow_amount,
            "capital_inflow_amount": capital_inflow_amount,
            "capital_outflow_amount": capital_outflow_amount,
            "contracts": len(bars),
            "main_contracts": len(main_bars),
            "liquid_contracts": len(ranking_valid),
        },
        "sectors": sectors,
        "rankings": {
            "gainers": [bar_item(b, c) for b, c in gainers],
            "losers": [bar_item(b, c) for b, c in losers],
            "volume": [bar_item(b) for b in volume_top],
            "open_interest": [bar_item(b) for b in oi_top],
        },
        "structure": structure,
        "term_structure": term_structure,
        "industry_chain": industry_chain,
        "event_calendar": event_calendar,
        "seats": {
            "long_increase_top": [seat_item(r, "long") for r in seat_long],
            "short_increase_top": [seat_item(r, "short") for r in seat_short],
            "watchlist": watch_seat_rows,
            "archive": seat_archive,
        },
        "watch_symbols": watch_bars,
        "data_quality": data_quality,
        "coverage_matrix": coverage_matrix,
        "dataset": {
            "count": dataset.get("count", 0),
            "summary": dataset.get("summary", {}),
            "top_net_delta": sorted(
                [r for r in dataset.get("rows", []) if r.get("archive_signal") and r["archive_signal"].get("netDelta") is not None],
                key=lambda x: abs(x["archive_signal"].get("netDelta") or 0),
                reverse=True,
            )[:10],
        },
        "intelligence": {
            "positioning": "日报型市场情报：收集资讯与数据，拆解异动原因，帮助投资者第一时间理解全市场情况；不替代实时行情软件，不构成交易建议。",
            "abnormal_cards": abnormal_cards,
            "tomorrow_watch": tomorrow_watch,
            "news_digest": news_digest,
            "watch_digest": watch_digest,
            "history_context": {
                "status": "ok" if any(x.get("status") == "ok" for x in history_context.values()) else "insufficient_history",
                "symbols": len(history_context),
            },
            "term_structure": term_structure,
            "industry_chain": industry_chain,
            "event_calendar": event_calendar,
        },
        "risk_flags": quality_flags(data_quality),
        "report_brief": report_brief,
        "report_sections": report_sections,
        "action_notes": build_action_notes(gap_analysis),
    }

    no_usable_market_data = len(bars) == 0 or len(main_bars) == 0
    if no_usable_market_data:
        no_data_summary = (
            f"{trade_date} 尚未形成有效期货日报：未找到可用日行情数据。"
            "请先执行数据诊断/自动补采；若补采仍失败，按覆盖矩阵中的缺口原因复核数据源。"
        )
        payload["meta"]["operational_status"] = "no_usable_market_data"
        payload["meta"]["operational_message"] = no_data_summary
        payload["overview"].update(
            {
                "score": 0,
                "stage": "无数据",
                "heat": "无数据｜待补采",
                "risk": 100,
                "direction": "无法判断",
                "summary": no_data_summary,
            }
        )
        payload["risk_flags"] = [no_data_summary, *payload.get("risk_flags", [])]
        payload["report_brief"] = {
            "title": f"期货日报 {trade_date}｜未形成有效日报",
            "conclusion": no_data_summary,
            "bullets": [
                {"label": "核心原因", "text": "日行情为空，市场温度、涨跌排行和异动拆解不可用。"},
                {"label": "下一步", "text": "打开数据诊断页执行 Retry Plan，或手动补采对应交易日行情。"},
                {"label": "安全提示", "text": "不会用旧数据或缺失数据伪造当天结论。"},
            ],
        }

    payload["push_digest"] = build_push_digest(payload)

    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        report = Report(trade_date=trade_date)
    report.status = "blocked" if no_usable_market_data else "generated"
    report.score = payload["overview"]["score"]
    report.summary = payload["overview"]["summary"]
    report.report_json = json.dumps(payload, ensure_ascii=False, default=str)
    report.generated_at = datetime.utcnow()
    report.updated_at = datetime.utcnow()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def previous_total_volume(db: Session, trade_date: str) -> float | None:
    prev_date = db.scalar(select(DailyBar.trade_date).where(DailyBar.trade_date < trade_date).group_by(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))
    if not prev_date:
        return None
    return sum(float(v or 0) for v in db.scalars(select(DailyBar.volume).where(DailyBar.trade_date == prev_date)).all())


def previous_total_open_interest_delta(db: Session, trade_date: str) -> float | None:
    prev_date = db.scalar(select(DailyBar.trade_date).where(DailyBar.trade_date < trade_date).group_by(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))
    if not prev_date:
        return None
    current = sum(float(v or 0) for v in db.scalars(select(DailyBar.open_interest).where(DailyBar.trade_date == trade_date)).all())
    previous = sum(float(v or 0) for v in db.scalars(select(DailyBar.open_interest).where(DailyBar.trade_date == prev_date)).all())
    return current - previous


def previous_main_open_interest_deltas(db: Session, trade_date: str, main_bars: list[DailyBar]) -> dict[tuple[str, str, str], float | None]:
    prev_date = db.scalar(select(DailyBar.trade_date).where(DailyBar.trade_date < trade_date).group_by(DailyBar.trade_date).order_by(desc(DailyBar.trade_date)).limit(1))
    if not prev_date:
        return {}
    prev_bars = list(db.scalars(select(DailyBar).where(DailyBar.trade_date == prev_date)))
    prev_by_contract = {
        (get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper(), str(bar.contract or "")): float(bar.open_interest or 0)
        for bar in prev_bars
    }
    deltas: dict[tuple[str, str, str], float | None] = {}
    for bar in main_bars:
        key = (get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper(), str(bar.contract or ""))
        previous = prev_by_contract.get(key)
        deltas[key] = None if previous is None else float(bar.open_interest or 0) - previous
    return deltas


def pick_main_bars(bars: list[DailyBar]) -> list[DailyBar]:
    grouped: dict[tuple[str, str], list[DailyBar]] = defaultdict(list)
    for bar in bars:
        grouped[(get_exchange_code(bar.symbol, bar.exchange), bar.symbol.upper())].append(bar)
    return [
        sorted(items, key=lambda x: ((x.volume or 0) * 0.65 + (x.open_interest or 0) * 0.35), reverse=True)[0]
        for items in grouped.values()
        if items
    ]


def is_liquid_bar(bar: DailyBar) -> bool:
    return (bar.volume or 0) >= LIQUID_MIN_VOLUME and (bar.open_interest or 0) >= LIQUID_MIN_OPEN_INTEREST


def build_report_sections(
    *,
    up_count: int,
    down_count: int,
    stage: str,
    score: float,
    structure: dict,
    seat_archive: dict,
    dataset: dict,
    data_quality: dict,
    gap_analysis: dict,
    seat_long: list[SeatRankRow],
    seat_short: list[SeatRankRow],
    abnormal_cards: list[dict] | None = None,
) -> list[dict]:
    breadth = structure.get("sector_breadth") or []
    active = sorted(breadth, key=lambda x: x.get("volume") or 0, reverse=True)[:3]
    active_text = "、".join(f"{x.get('name')}成交{human_num(x.get('volume'))}" for x in active) or "暂无明显活跃板块"
    abnormal_cards = abnormal_cards or []
    abnormal_top = "、".join(f"{x.get('name') or x.get('symbol')}：{x.get('signal')}" for x in abnormal_cards[:3]) or "暂无显著异动卡片"
    archive_top = (seat_archive.get("net_delta_top") or [])[:3]
    archive_text = "、".join(f"{x.get('displayName') or x.get('name')}净变{signed_num(x.get('netDelta'))}" for x in archive_top) or "结构化席位信号暂不突出"
    long_text = "、".join(f"{r.variety}{r.long_party_name}+{human_num(r.long_open_interest_chg)}" for r in seat_long[:3]) or "多头增仓信号不足"
    short_text = "、".join(f"{r.variety}{r.short_party_name}+{human_num(r.short_open_interest_chg)}" for r in seat_short[:3]) or "空头增仓信号不足"
    actionable = gap_analysis.get("actionable_count", 0)
    explained = gap_analysis.get("explained_count", 0)
    coverage = data_quality.get("overall_coverage_pct", data_quality.get("coverage_pct", 0))
    quality_summary = data_quality.get("summary") or f"基础数据覆盖率 {coverage}%"
    dataset_count = dataset.get("count", 0)

    return [
        {
            "title": "市场结论",
            "tone": market_temperature_tone(stage),
            "body": f"当前市场温度为{stage}，综合温度 {score}。该分数衡量活跃度与资金博弈强度，不等同于看多；主力合约流动性过滤后，上涨 {up_count} 个、下跌 {down_count} 个；活跃度主要集中在 {active_text}。",
        },
        {
            "title": "主线机会",
            "tone": "positive",
            "body": f"从席位与成交结构看，重点关注两条线：一是成交/持仓集中的活跃板块；二是结构化席位净变化靠前的品种。当前结构信号：{archive_text}。多头增仓靠前：{long_text}。",
        },
        {
            "title": "异动拆解",
            "tone": "info",
            "body": f"日报重点不替代实时行情，而是把价格、持仓、仓单/库存、席位和资讯线索汇总为观察清单。当前优先观察：{abnormal_top}。",
        },
        {
            "title": "风险提示",
            "tone": "warning",
            "body": f"空头增仓与结构信号需要同步观察，避免只看成交热度。当前空头增仓靠前：{short_text}。若板块成交放大但结构席位方向不一致，应优先按分化行情处理。",
        },
        {
            "title": "数据可信度",
            "tone": "info" if actionable == 0 else "warning",
            "body": f"本次品种级数据集覆盖 {dataset_count} 个品种；{quality_summary}。数据缺口共 {gap_analysis.get('count', 0)} 条，其中可行动缺口 {actionable} 条、已解释缺口 {explained} 条。当前结论适合作为盘后复盘和次日观察清单，不应单独作为交易依据。",
        },
    ]



def build_abnormal_cards(dataset: dict, limit: int = 12, news_digest: dict | None = None, history_context: dict | None = None) -> list[dict]:
    """Build explainable variety-level abnormal cards for the daily intelligence view.

    The card is a reading priority, not a trading signal. It rewards facts that
    make a variety worth opening in the daily report: large price move, high
    participation, seat divergence, warehouse/basis pressure, and capital flow.
    """
    news_by_symbol = index_news_by_symbol((news_digest or {}).get("items") or [])
    viewpoints_by_symbol = {str(v.get("symbol") or "").upper(): v for v in (news_digest or {}).get("viewpoints") or []}
    cards = []
    for row in dataset.get("rows", []) or []:
        chg = safe_num(row.get("main_change_pct"))
        volume = safe_num(row.get("total_volume") or row.get("main_volume"))
        oi = safe_num(row.get("total_open_interest") or row.get("main_open_interest"))
        archive = row.get("archive_signal") or {}
        seat = row.get("seat") or {}
        external = row.get("external_signals") or {}
        warehouse = external.get("warehouse_receipt") or {}
        basis = external.get("basis") or {}
        capital = external.get("capital_flow") or {}
        net_delta = safe_num(archive.get("netDelta") if archive else seat.get("net_delta_top20"))
        long_short_ratio = safe_num(archive.get("longShortRatio")) if archive else None
        warehouse_delta = safe_num(warehouse.get("increase_number"))
        warehouse_ratio = safe_num(warehouse.get("increase_ratio"))
        basis_rate = safe_num(basis.get("basis_rate"))
        capital_yi = safe_num(capital.get("amount_yi"))

        symbol = str(row.get("symbol") or "").upper()
        symbol_history = (history_context or {}).get(symbol) or {}
        related_news = news_by_symbol.get(symbol, [])[:3]
        viewpoint = viewpoints_by_symbol.get(symbol)
        dimensions = score_dimensions(chg, volume, oi, net_delta, long_short_ratio, warehouse_delta, warehouse_ratio, basis_rate, capital_yi, len(related_news))
        dimensions = merge_history_dimensions(dimensions, symbol_history)
        score = sum(x["score"] for x in dimensions)
        if score <= 0:
            continue
        signal, bias = classify_abnormal_signal(chg, net_delta, warehouse_delta, basis_rate)
        reasons = build_reasons(chg, net_delta, long_short_ratio, warehouse_delta, warehouse_ratio, basis_rate, capital_yi)
        watch_next = build_watch_next(chg, net_delta, warehouse_delta, basis_rate, related_news)
        evidence_chain = build_evidence_chain(
            chg=chg,
            close=safe_num(row.get("main_close")),
            volume=volume,
            oi=oi,
            net_delta=net_delta,
            long_short_ratio=long_short_ratio,
            warehouse_delta=warehouse_delta,
            warehouse_ratio=warehouse_ratio,
            basis_rate=basis_rate,
            capital_yi=capital_yi,
            viewpoint=viewpoint,
            related_news=related_news,
            watch_next=watch_next,
        )
        cards.append({
            "exchange": row.get("exchange"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "sector": row.get("sector"),
            "main_contract": row.get("main_contract"),
            "score": round(score, 2),
            "bias": bias,
            "signal": signal,
            "reasons": reasons[:6],
            "dimensions": dimensions,
            "evidence_chain": evidence_chain,
            "watch_next": watch_next,
            "related_news": related_news,
            "news_viewpoint": viewpoint,
            "history_context": symbol_history,
            "source_quality": row.get("quality") or {},
        })
    cards.sort(key=lambda x: x["score"], reverse=True)
    return cards[:limit]


def score_dimensions(chg, volume, oi, net_delta, long_short_ratio, warehouse_delta, warehouse_ratio, basis_rate, capital_yi, news_count: int = 0) -> list[dict]:
    dims = []
    def add(name: str, value, score: float, note: str):
        if score > 0:
            dims.append({"name": name, "value": value, "score": round(score, 2), "note": note})
    add("价格波动", chg, min(abs(chg or 0) * 2.2, 18), "主力合约涨跌幅越大，越需要解释")
    add("成交活跃", volume, min((volume or 0) / 1_000_000, 8), "成交放大代表市场关注度")
    add("持仓规模", oi, min((oi or 0) / 500_000, 8), "持仓规模大，后续影响更广")
    add("席位净变化", net_delta, min(abs(net_delta or 0) / 10_000, 14), "席位净多/净空变化提供结构线索")
    if long_short_ratio is not None:
        add("多空比极值", long_short_ratio, min(abs(long_short_ratio - 1) * 5, 8), "多空比偏离 1 越多，结构越极端")
    add("仓单变化", warehouse_delta, min(abs(warehouse_delta or 0) / 1000, 10), "仓单变化可解释供需边际变化")
    add("仓单变动率", warehouse_ratio, min(abs(warehouse_ratio or 0) * 0.4, 8), "仓单变动率用于发现小品种突变")
    add("基差偏离", basis_rate, min(abs(basis_rate or 0) * 0.8, 8), "基差偏离提示现货/期货矛盾")
    add("沉淀资金", capital_yi, min(abs(capital_yi or 0) * 1.1, 8), "资金沉淀越大，品种关注度越高")
    add("资讯热度", news_count, min((news_count or 0) * 2.5, 8), "相关新闻越多，越需要结合事件解释")
    dims.sort(key=lambda x: x["score"], reverse=True)
    return dims[:5]


def merge_history_dimensions(dimensions: list[dict], history_context: dict | None) -> list[dict]:
    highlights = (history_context or {}).get("highlights") or []
    dims = list(dimensions)
    for item in highlights[:2]:
        percentile = safe_num(item.get("percentile"))
        if percentile is None:
            continue
        extremity = abs(percentile - 50) / 50
        if extremity < 0.7:
            continue
        dims.append({
            "name": f"历史{item.get('label')}",
            "value": percentile,
            "score": round(min(4 + extremity * 6, 10), 2),
            "note": item.get("note") or f"近 {item.get('window')} 日分位 {percentile}%",
        })
    dims.sort(key=lambda x: x["score"], reverse=True)
    return dims[:6]


def classify_abnormal_signal(chg, net_delta, warehouse_delta, basis_rate) -> tuple[str, str]:
    c = chg or 0
    n = net_delta or 0
    w = warehouse_delta or 0
    b = basis_rate or 0
    if c >= 1 and n > 0:
        return "上涨 + 席位净多增加，偏主动多头线索", "positive"
    if c >= 1 and n < 0:
        return "上涨但席位净变化偏空，可能存在分歧", "mixed"
    if c <= -1 and n < 0:
        return "下跌 + 席位净空增加，偏空头增仓线索", "negative"
    if c <= -1 and n > 0:
        return "下跌但席位净变化偏多，需防分歧/换手", "mixed"
    if w < 0 and c >= 0:
        return "仓单下降且价格不弱，关注供应收紧验证", "positive"
    if w > 0 and c <= 0:
        return "仓单增加且价格偏弱，关注库存压力", "negative"
    if abs(b) >= 3:
        return "基差偏离较大，关注期现修复", "mixed"
    if abs(c) >= 1:
        return "价格异动，等待持仓/仓单/资讯确认", "mixed"
    return "结构活跃，适合列入次日观察", "neutral"


def build_reasons(chg, net_delta, long_short_ratio, warehouse_delta, warehouse_ratio, basis_rate, capital_yi) -> list[str]:
    reasons = []
    if chg is not None:
        reasons.append(f"主力涨跌{signed_pct(chg)}")
    if net_delta is not None:
        reasons.append(f"席位净变化{signed_num(net_delta)}")
    if long_short_ratio is not None:
        reasons.append(f"多空比{long_short_ratio:.2f}")
    if warehouse_delta is not None:
        text = f"仓单变化{signed_num(warehouse_delta)}"
        if warehouse_ratio is not None:
            text += f"（{signed_pct(warehouse_ratio)}）"
        reasons.append(text)
    if basis_rate is not None:
        reasons.append(f"基差率{signed_pct(basis_rate)}")
    if capital_yi is not None:
        reasons.append(f"沉淀资金约{capital_yi:.2f}亿")
    return reasons or ["价格/持仓/外部数据出现可观察变化"]


def build_evidence_chain(
    *,
    chg,
    close,
    volume,
    oi,
    net_delta,
    long_short_ratio,
    warehouse_delta,
    warehouse_ratio,
    basis_rate,
    capital_yi,
    viewpoint: dict | None,
    related_news: list[dict] | None,
    watch_next: str,
) -> list[dict]:
    """Return a compact price → position → physical → news → next-day evidence chain."""
    chain: list[dict] = []
    price_bits = []
    if close is not None:
        price_bits.append(f"收盘 {close:g}")
    if chg is not None:
        price_bits.append(f"涨跌 {signed_pct(chg)}")
    if volume is not None:
        price_bits.append(f"成交 {format_compact_num(volume)}")
    if oi is not None:
        price_bits.append(f"持仓 {format_compact_num(oi)}")
    chain.append({"key": "price", "label": "价格/量仓", "text": "；".join(price_bits) or "暂无价格/量仓证据"})

    seat_bits = []
    if net_delta is not None:
        seat_bits.append(f"净变化 {signed_num(net_delta)}")
    if long_short_ratio is not None:
        seat_bits.append(f"多空比 {long_short_ratio:.2f}")
    chain.append({"key": "seat", "label": "席位", "text": "；".join(seat_bits) or "暂无席位证据"})

    physical_bits = []
    if warehouse_delta is not None:
        text = f"仓单 {signed_num(warehouse_delta)}"
        if warehouse_ratio is not None:
            text += f"（{signed_pct(warehouse_ratio)}）"
        physical_bits.append(text)
    if basis_rate is not None:
        physical_bits.append(f"基差率 {signed_pct(basis_rate)}")
    if capital_yi is not None:
        physical_bits.append(f"沉淀资金 {capital_yi:.2f}亿")
    chain.append({"key": "physical", "label": "基差/仓单", "text": "；".join(physical_bits) or "暂无基差/仓单证据"})

    news_text = "暂无资讯观点"
    if viewpoint and viewpoint.get("summary"):
        news_text = str(viewpoint.get("summary"))
    elif related_news:
        first = related_news[0] or {}
        news_text = f"关联资讯 {len(related_news)} 条：{first.get('title') or first.get('source') or '待复核'}"
    chain.append({"key": "news", "label": "资讯观点", "text": news_text})
    chain.append({"key": "next", "label": "明日观察", "text": watch_next or "观察价格、持仓与资讯是否继续验证。"})
    return chain


def format_compact_num(value) -> str:
    n = safe_num(value)
    if n is None:
        return "-"
    if abs(n) >= 100000000:
        return f"{n / 100000000:.2f}亿"
    if abs(n) >= 10000:
        return f"{n / 10000:.1f}万"
    return f"{n:.0f}"



def build_watch_digest(dataset: dict, watch_symbols: list[WatchSymbol], abnormal_cards: list[dict], news_digest: dict | None = None) -> dict:
    """Build a focused daily report for the user's watchlist varieties."""
    default_watch_codes = ["TA", "RU", "PX", "JD", "CJ", "A", "NI", "RB", "PB"]
    configured_codes = [w.symbol.upper() for w in watch_symbols if getattr(w, "enabled", True)]
    # Merge configured watchlist with Rey's current futures-panel watch pool so
    # the digest stays useful even before the settings page is fully populated.
    watch_codes = list(dict.fromkeys([*configured_codes, *default_watch_codes]))
    rows_by_symbol = {str(r.get("symbol") or "").upper(): r for r in dataset.get("rows", []) or []}
    cards_by_symbol = {str(c.get("symbol") or "").upper(): c for c in abnormal_cards or []}
    viewpoints_by_symbol = {str(v.get("symbol") or "").upper(): v for v in (news_digest or {}).get("viewpoints") or []}
    news_by_symbol = index_news_by_symbol((news_digest or {}).get("items") or [])
    items = []
    for symbol in watch_codes:
        row = rows_by_symbol.get(symbol)
        card = cards_by_symbol.get(symbol)
        viewpoint = viewpoints_by_symbol.get(symbol)
        if not row and not card and not viewpoint:
            items.append({
                "symbol": symbol,
                "name": get_variety_name(symbol),
                "status": "missing",
                "summary": "暂无当日数据，需等待采集或检查数据源覆盖。",
                "watch_next": "复核行情、席位和增强源是否覆盖该品种。",
            })
            continue
        external = (row or {}).get("external_signals") or {}
        seat = (row or {}).get("seat") or {}
        archive = (row or {}).get("archive_signal") or {}
        chg = safe_num((row or {}).get("main_change_pct"))
        net_delta = safe_num(archive.get("netDelta") if archive else seat.get("net_delta_top20"))
        warehouse = external.get("warehouse_receipt") or {}
        basis = external.get("basis") or {}
        capital = external.get("capital_flow") or {}
        reasons = build_reasons(
            chg,
            net_delta,
            safe_num(archive.get("longShortRatio")) if archive else None,
            safe_num(warehouse.get("increase_number")),
            safe_num(warehouse.get("increase_ratio")),
            safe_num(basis.get("basis_rate")),
            safe_num(capital.get("amount_yi")),
        )
        warehouse_delta = safe_num(warehouse.get("increase_number"))
        warehouse_ratio = safe_num(warehouse.get("increase_ratio"))
        basis_rate = safe_num(basis.get("basis_rate"))
        capital_yi = safe_num(capital.get("amount_yi"))
        signal = card.get("signal") if card else classify_abnormal_signal(chg, net_delta, warehouse_delta, basis_rate)[0]
        watch_next = (card or {}).get("watch_next") or build_watch_next(chg, net_delta, warehouse_delta, basis_rate, news_by_symbol.get(symbol, []))
        evidence_chain = (card or {}).get("evidence_chain") or build_evidence_chain(
            chg=chg,
            close=safe_num((row or {}).get("main_close")),
            volume=safe_num((row or {}).get("total_volume") or (row or {}).get("main_volume")),
            oi=safe_num((row or {}).get("total_open_interest") or (row or {}).get("main_open_interest")),
            net_delta=net_delta,
            long_short_ratio=safe_num(archive.get("longShortRatio")) if archive else None,
            warehouse_delta=warehouse_delta,
            warehouse_ratio=warehouse_ratio,
            basis_rate=basis_rate,
            capital_yi=capital_yi,
            viewpoint=viewpoint,
            related_news=news_by_symbol.get(symbol, []),
            watch_next=watch_next,
        )
        items.append({
            "symbol": symbol,
            "name": (row or {}).get("name") or get_variety_name(symbol),
            "exchange": (row or {}).get("exchange"),
            "sector": (row or {}).get("sector"),
            "main_contract": (row or {}).get("main_contract"),
            "change_pct": chg,
            "main_close": (row or {}).get("main_close"),
            "volume": (row or {}).get("total_volume") or (row or {}).get("main_volume"),
            "open_interest": (row or {}).get("total_open_interest") or (row or {}).get("main_open_interest"),
            "signal": signal,
            "bias": (card or {}).get("bias") or (viewpoint or {}).get("bias") or "neutral",
            "reasons": reasons[:6],
            "evidence_chain": evidence_chain,
            "news_viewpoint": viewpoint,
            "related_news": news_by_symbol.get(symbol, [])[:3],
            "watch_next": watch_next,
            "status": "ok",
        })
    ok_items = [x for x in items if x.get("status") == "ok"]
    summary = build_watch_digest_summary(ok_items, items)
    return {"symbols": watch_codes, "items": items, "summary": summary}


def build_watch_digest_summary(ok_items: list[dict], all_items: list[dict]) -> str:
    if not all_items:
        return "暂无自选品种。"
    if not ok_items:
        return "自选品种暂无有效数据，需先完成行情/增强源采集。"
    strong = [x for x in ok_items if safe_num(x.get("change_pct")) is not None and safe_num(x.get("change_pct")) > 0]
    weak = [x for x in ok_items if safe_num(x.get("change_pct")) is not None and safe_num(x.get("change_pct")) < 0]
    news = [x for x in ok_items if x.get("news_viewpoint")]
    hot = sorted(ok_items, key=lambda x: abs(safe_num(x.get("change_pct")) or 0), reverse=True)[:3]
    hot_text = "、".join(f"{x.get('name')}({signed_pct(x.get('change_pct'))})" for x in hot if x.get("change_pct") is not None) or "暂无明显价格异动"
    return f"自选品种覆盖 {len(ok_items)}/{len(all_items)} 个；上涨 {len(strong)} 个、下跌 {len(weak)} 个；重点波动：{hot_text}；其中 {len(news)} 个品种有关联资讯观点。"

def build_tomorrow_watch(abnormal_cards: list[dict], data_quality: dict, gap_analysis: dict, news_digest: dict | None = None) -> list[dict]:
    """Build a next-day watch list from existing report facts.

    The goal is not to predict prices, but to tell the user what evidence should
    be checked next: price continuation, seat confirmation, physical-market
    validation, news follow-through, and data-quality gaps.
    """
    items: list[dict] = []

    def add_item(*, type_: str, title: str, body: str, category: str, priority: str = "normal", symbol: str | None = None, name: str | None = None, evidence: list[str] | None = None, impact: str = "") -> None:
        if not title or not body:
            return
        key = (type_, symbol or "", title)
        if any((x.get("type"), x.get("symbol") or "", x.get("title")) == key for x in items):
            return
        items.append({
            "type": type_,
            "category": category,
            "title": title,
            "body": body,
            "priority": priority,
            "symbol": symbol,
            "name": name,
            "evidence": [x for x in (evidence or []) if x][:4],
            "impact": impact,
        })

    for card in abnormal_cards[:6]:
        evidence_chain = card.get("evidence_chain") or []
        evidence_text = [str(x.get("text") or "") for x in evidence_chain if x.get("text") and "暂无" not in str(x.get("text"))]
        labels = {str(x.get("key") or "") for x in evidence_chain}
        dims = {str(x.get("name") or "") for x in card.get("dimensions") or []}
        category = "价格延续"
        if "席位净变化" in dims or "seat" in labels:
            category = "席位验证"
        if "仓单变化" in dims or "基差偏离" in dims or "physical" in labels:
            category = "仓单/基差验证"
        if "资讯热度" in dims or card.get("news_viewpoint"):
            category = "资讯验证"
        name = card.get("name") or card.get("symbol") or "重点品种"
        watch_next = card.get("watch_next") or "观察价格、持仓和资讯是否继续同向验证。"
        body = f"{watch_next}"
        if card.get("signal"):
            body = f"{card.get('signal')}；{body}"
        add_item(
            type_="variety",
            category=category,
            title=f"{name}后续验证",
            body=body,
            priority="high" if card.get("score", 0) >= 20 else "normal",
            symbol=card.get("symbol"),
            name=name,
            evidence=evidence_text,
            impact="若明天继续同向验证，这个品种应保持在重点观察名单。",
        )

    bad_exchanges = [x for x in (data_quality or {}).get("exchanges", []) if x.get("status") != "ok"]
    if bad_exchanges:
        names = "、".join(str(x.get("exchange")) for x in bad_exchanges[:6])
        notes = [f"{x.get('exchange')}：{x.get('note') or '部分数据缺失'}" for x in bad_exchanges[:4]]
        add_item(
            type_="data_quality",
            category="数据复核",
            title="先确认缺失数据",
            body="优先复核缺失/异常交易所：" + names,
            priority="high",
            evidence=notes,
            impact="数据缺失会降低席位、仓单或基差相关结论的权重。",
        )

    if gap_analysis.get("actionable_count", 0):
        add_item(
            type_="data_gap",
            category="数据复核",
            title="补齐可处理的数据缺口",
            body=f"仍有 {gap_analysis.get('actionable_count')} 个可尝试补齐的数据项，修复前相关结论要打折。",
            priority="high",
            evidence=["优先处理能影响行情、席位或仓单判断的数据项。"],
            impact="补齐后日报结论会更可靠。",
        )

    news_summary = (news_digest or {}).get("summary") or {}
    viewpoints = (news_digest or {}).get("viewpoints") or []
    if viewpoints:
        bias_label = {"positive": "偏多", "negative": "偏空", "mixed": "分歧", "neutral": "中性"}
        hot = "、".join(f"{v.get('name') or v.get('symbol')}({bias_label.get(v.get('bias'), '中性')})" for v in viewpoints[:5])
        add_item(
            type_="viewpoint",
            category="资讯验证",
            title="复核资讯观点是否发酵",
            body=f"重点看这些资讯观点是否继续影响盘面：{hot}。",
            priority="normal",
            evidence=[str(v.get("summary") or "") for v in viewpoints[:3]],
            impact="若资讯与价格/席位同向，异动可信度会提高。",
        )
    if news_summary.get("top_symbols"):
        top = "、".join(f"{sym}({count})" for sym, count in news_summary.get("top_symbols", [])[:5])
        add_item(
            type_="news",
            category="资讯热度",
            title="跟踪高频资讯品种",
            body=f"重点复核资讯高频品种：{top}，判断是否与价格/持仓异动共振。",
            priority="normal",
            evidence=["资讯热度高但价格未确认时，先观察，不急着下结论。"],
            impact="适合用来发现可能继续发酵的主题。",
        )

    add_item(
        type_="calendar",
        category="交易日历",
        title="留意交易所公告",
        body="关注保证金、涨跌停、交割月、最后交易日和夜盘安排。",
        priority="normal",
        evidence=["临近交割或保证金调整时，波动和持仓变化可能放大。"],
        impact="主要影响短线波动和持仓风险。",
    )
    add_item(
        type_="macro",
        category="宏观/产业事件",
        title="留意宏观和产业数据",
        body="能化关注 EIA/OPEC，农产品关注 USDA/天气，贵金属关注美元与利率数据。",
        priority="normal",
        evidence=["事件日附近，价格异动更需要结合外部变量验证。"],
        impact="主要用于解释隔夜或次日跳空/放量。",
    )

    items.sort(key=lambda x: 0 if x.get("priority") == "high" else 1)
    return items[:10]


def safe_num(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def abnormal_score(chg, volume, oi, net_delta, warehouse_delta, basis_rate, capital_yi) -> float:
    # Backward-compatible wrapper used by older tests/imports.
    return sum(x["score"] for x in score_dimensions(safe_num(chg), safe_num(volume), safe_num(oi), safe_num(net_delta), None, safe_num(warehouse_delta), None, safe_num(basis_rate), safe_num(capital_yi), 0))


def classify_price_oi(chg, oi) -> str:
    # Backward-compatible wrapper used by older UI/tests.
    return classify_abnormal_signal(safe_num(chg), None, None, None)[0]


def build_watch_next(chg, net_delta, warehouse_delta, basis_rate, related_news: list[dict] | None = None) -> str:
    notes = []
    c = safe_num(chg)
    n = safe_num(net_delta)
    w = safe_num(warehouse_delta)
    b = safe_num(basis_rate)
    if c is not None and abs(c) >= 2:
        notes.append("次日价格是否延续")
    if n is not None:
        notes.append("席位净多/净空是否连续")
    if w is not None:
        notes.append("仓单变化是否与价格同向验证")
    if b is not None:
        notes.append("基差是否继续修复或扩大")
    if related_news:
        notes.append("相关新闻是否继续发酵")
    return "；".join(notes) or "等待更多数据确认"


def index_news_by_symbol(items: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        compact = {
            "source": item.get("source"),
            "title": item.get("title"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "importance": item.get("importance"),
        }
        for sym in item.get("symbols") or []:
            out[str(sym).upper()].append(compact)
    for rows in out.values():
        rows.sort(key=lambda x: (x.get("importance") or 0, x.get("published_at") or ""), reverse=True)
    return out


def signed_pct(value) -> str:
    try:
        n = float(value)
        return f"{n:+.2f}%"
    except Exception:
        return str(value)


def build_report_brief(sections: list[dict], stage: str, score: float) -> dict:
    by_title = {x.get("title"): x for x in sections}
    conclusion = by_title.get("市场结论", {}).get("body", "暂无结论")
    opportunity = by_title.get("主线机会", {}).get("body", "暂无机会线索")
    risk = by_title.get("风险提示", {}).get("body", "暂无风险提示")
    data = by_title.get("数据可信度", {}).get("body", "暂无数据说明")
    return {
        "title": f"{stage}｜综合分 {score}",
        "conclusion": conclusion,
        "bullets": [
            {"label": "重点关注", "text": pick_after(opportunity, "当前结构信号：") or shorten_sentence(opportunity)},
            {"label": "风险提示", "text": pick_after(risk, "当前空头增仓靠前：") or shorten_sentence(risk)},
            {"label": "数据可信度", "text": compact_data_text(data)},
        ],
    }


def pick_after(text: str, marker: str) -> str:
    text = str(text or "")
    if marker not in text:
        return ""
    value = text.split(marker, 1)[1].split("。", 1)[0]
    return shorten_sentence(value, 56)


def compact_data_text(text: str) -> str:
    text = str(text or "")
    if "数据缺口共" in text:
        tail = text.split("数据缺口共", 1)[1].split("。", 1)[0]
        return shorten_sentence(f"数据缺口共{tail}", 64)
    return shorten_sentence(text, 64)


def shorten_sentence(text: str, max_len: int = 56) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip("，。；、 ") + "…"


def build_action_notes(gap_analysis: dict) -> list[str]:
    if gap_analysis.get("actionable_count", 0) == 0:
        return ["当前数据缺口均已解释，无待处理 actionable 数据缺口。", "日报结论用于复盘和观察清单，不构成交易建议。"]
    return [f"仍有 {gap_analysis.get('actionable_count')} 个可行动数据缺口，需优先修复后再提高结论权重。", "日报结论用于复盘和观察清单，不构成交易建议。"]


def human_num(value) -> str:
    try:
        n = float(value or 0)
    except Exception:
        return "-"
    if abs(n) >= 100000000:
        return f"{n / 100000000:.2f}亿"
    if abs(n) >= 10000:
        return f"{n / 10000:.1f}万"
    return f"{n:.0f}"


def signed_num(value) -> str:
    text = human_num(value)
    try:
        return f"+{text}" if float(value or 0) > 0 else text
    except Exception:
        return text


def quality_flags(data_quality: dict) -> list[str]:
    if data_quality.get("status") == "ok" and not data_quality.get("fallback_used"):
        return []
    summary = data_quality.get("summary") or f"数据覆盖 {data_quality.get('coverage_pct', 0)}%。"
    flags = [summary]
    failed = data_quality.get("failed_exchanges") or [x["exchange"] for x in data_quality.get("exchanges", []) if x.get("status") == "failed"]
    if failed:
        flags.append("失败交易所：" + "、".join(failed))
    if data_quality.get("fallback_used"):
        flags.append(f"席位数据含 fallback 补充：{data_quality.get('fallback_used')} 个交易所。")
    return flags


def seat_watch_item(row: SeatRankRow) -> dict:
    return {
        "exchange": row.exchange,
        "variety": row.variety,
        "contract": row.contract,
        "rank": row.rank,
        "vol_party_name": row.vol_party_name,
        "vol": row.vol,
        "vol_chg": row.vol_chg,
        "long_party_name": row.long_party_name,
        "long_open_interest": row.long_open_interest,
        "long_open_interest_chg": row.long_open_interest_chg,
        "short_party_name": row.short_party_name,
        "short_open_interest": row.short_open_interest,
        "short_open_interest_chg": row.short_open_interest_chg,
    }


def seat_item(row: SeatRankRow, side: str) -> dict:
    return {
        "exchange": row.exchange,
        "variety": row.variety,
        "contract": row.contract,
        "rank": row.rank,
        "seat": row.long_party_name if side == "long" else row.short_party_name,
        "value": row.long_open_interest if side == "long" else row.short_open_interest,
        "change": row.long_open_interest_chg if side == "long" else row.short_open_interest_chg,
    }
