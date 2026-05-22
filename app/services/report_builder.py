from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.metadata.contract_specs import get_point_value
from app.metadata.variety_meta import get_exchange_code, get_variety_name
from app.models import DailyBar, Report, SeatRankRow, WatchSymbol, SeatWatchlist
from app.services.data_mart import build_variety_dataset, materialize_variety_dataset
from app.services.data_quality import build_data_quality
from app.services.gap_analysis import build_gap_analysis
from app.services.seat_archive import load_archive_summary
from app.services.structure import build_structure, pct_change, sector_for


from app.version import VERSION

REPORT_SCHEMA_VERSION = 2
LIQUID_MIN_VOLUME = 1000
LIQUID_MIN_OPEN_INTEREST = 1000


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
    heat = round(up_count / valid_count * 100, 1)
    risk = round(down_count / valid_count * 100, 1)
    score = round((heat + (100 - risk)) / 2, 1)
    stage = "偏强" if score >= 65 else "偏弱" if score <= 40 else "分化"

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
    seat_archive = load_archive_summary(trade_date)
    dataset = build_variety_dataset(db, trade_date)
    materialize_variety_dataset(db, trade_date)
    gap_analysis = build_gap_analysis(db, trade_date)
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
    )

    payload = {
        "date": trade_date,
        "meta": {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "version": VERSION, "report_schema_version": REPORT_SCHEMA_VERSION},
        "overview": {
            "score": score,
            "stage": stage,
            "heat": heat,
            "risk": risk,
            "summary": report_sections[0]["body"],
        },
        "market": {"up_count": up_count, "down_count": down_count, "turnover": turnover, "volume": volume, "contracts": len(bars), "main_contracts": len(main_bars), "liquid_contracts": len(ranking_valid)},
        "sectors": sectors,
        "rankings": {
            "gainers": [bar_item(b, c) for b, c in gainers],
            "losers": [bar_item(b, c) for b, c in losers],
            "volume": [bar_item(b) for b in volume_top],
            "open_interest": [bar_item(b) for b in oi_top],
        },
        "structure": structure,
        "seats": {
            "long_increase_top": [seat_item(r, "long") for r in seat_long],
            "short_increase_top": [seat_item(r, "short") for r in seat_short],
            "watchlist": watch_seat_rows,
            "archive": seat_archive,
        },
        "watch_symbols": watch_bars,
        "data_quality": data_quality,
        "dataset": {
            "count": dataset.get("count", 0),
            "summary": dataset.get("summary", {}),
            "top_net_delta": sorted(
                [r for r in dataset.get("rows", []) if r.get("archive_signal") and r["archive_signal"].get("netDelta") is not None],
                key=lambda x: abs(x["archive_signal"].get("netDelta") or 0),
                reverse=True,
            )[:10],
        },
        "risk_flags": quality_flags(data_quality),
        "report_sections": report_sections,
        "action_notes": build_action_notes(gap_analysis),
    }

    report = db.scalar(select(Report).where(Report.trade_date == trade_date))
    if not report:
        report = Report(trade_date=trade_date)
    report.status = "generated"
    report.score = score
    report.summary = payload["overview"]["summary"]
    report.report_json = json.dumps(payload, ensure_ascii=False, default=str)
    report.generated_at = datetime.utcnow()
    report.updated_at = datetime.utcnow()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


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
) -> list[dict]:
    breadth = structure.get("sector_breadth") or []
    active = sorted(breadth, key=lambda x: x.get("volume") or 0, reverse=True)[:3]
    active_text = "、".join(f"{x.get('name')}成交{human_num(x.get('volume'))}" for x in active) or "暂无明显活跃板块"
    archive_top = (seat_archive.get("net_delta_top") or [])[:3]
    archive_text = "、".join(f"{x.get('displayName') or x.get('name')}净变{signed_num(x.get('netDelta'))}" for x in archive_top) or "结构化席位信号暂不突出"
    long_text = "、".join(f"{r.variety}{r.long_party_name}+{human_num(r.long_open_interest_chg)}" for r in seat_long[:3]) or "多头增仓信号不足"
    short_text = "、".join(f"{r.variety}{r.short_party_name}+{human_num(r.short_open_interest_chg)}" for r in seat_short[:3]) or "空头增仓信号不足"
    actionable = gap_analysis.get("actionable_count", 0)
    explained = gap_analysis.get("explained_count", 0)
    coverage = data_quality.get("coverage_pct", 0)
    dataset_count = dataset.get("count", 0)

    return [
        {
            "title": "市场结论",
            "tone": "neutral" if stage == "分化" else "positive" if stage == "偏强" else "negative",
            "body": f"当前市场状态为{stage}，综合分 {score}。主力合约流动性过滤后，上涨 {up_count} 个、下跌 {down_count} 个；活跃度主要集中在 {active_text}。",
        },
        {
            "title": "主线机会",
            "tone": "positive",
            "body": f"从席位与成交结构看，重点关注两条线：一是成交/持仓集中的活跃板块；二是结构化席位净变化靠前的品种。当前结构信号：{archive_text}。多头增仓靠前：{long_text}。",
        },
        {
            "title": "风险提示",
            "tone": "warning",
            "body": f"空头增仓与结构信号需要同步观察，避免只看成交热度。当前空头增仓靠前：{short_text}。若板块成交放大但结构席位方向不一致，应优先按分化行情处理。",
        },
        {
            "title": "数据可信度",
            "tone": "info" if actionable == 0 else "warning",
            "body": f"本次品种级数据集覆盖 {dataset_count} 个品种，基础数据覆盖率 {coverage}%。数据缺口共 {gap_analysis.get('count', 0)} 条，其中可行动缺口 {actionable} 条、已解释缺口 {explained} 条。当前结论适合作为盘后复盘和次日观察清单，不应单独作为交易依据。",
        },
    ]


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
    if data_quality.get("status") == "ok":
        return []
    flags = [f"数据覆盖 {data_quality.get('coverage_pct', 0)}%，部分交易所采集失败。"]
    failed = [x["exchange"] for x in data_quality.get("exchanges", []) if x.get("status") == "failed"]
    if failed:
        flags.append("失败交易所：" + "、".join(failed))
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
