from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.metadata.variety_meta import VARIETY_META_BY_SYMBOL
from app.models import MarketSnapshot
from app.services.collector import finish_crawler_run, start_crawler_run, update_data_gap

SOURCE = "public_news"
UA = "Mozilla/5.0 (FuturesDaily/0.1; +https://localhost)"

NEWS_SOURCES = [
    {
        "name": "东方财富期货",
        "url": "https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery1124&param={param}",
        "kind": "eastmoney_search",
        "queries": ["期货 市场", "商品期货", "期货 持仓", "期货 仓单", "期货 基差"],
    },
    {
        "name": "新浪期货",
        "url": "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=1687&num=20&page=1",
        "kind": "sina_roll",
        "queries": [],
    },
    {"name": "曲合快讯", "url": "https://kuaixun.quheqihuo.com/", "kind": "quhe_kuaixun", "queries": []},
    {"name": "七禾网", "url": "https://www.7hcn.com/", "kind": "article_links", "queries": []},
    {"name": "同花顺期货", "url": "https://futures.10jqka.com.cn/", "kind": "article_links_gbk", "queries": []},
    {"name": "华尔街见闻", "url": "https://wallstreetcn.com/live", "kind": "article_links", "queries": []},
    {"name": "财联社", "url": "https://www.cls.cn/", "kind": "cls_depth", "queries": []},
]
MAX_NEWS_ITEMS = 80
MAX_NEWS_WORKERS = 6


def collect_news_digest(db: Session, trade_date: str) -> dict[str, Any]:
    """Collect lightweight futures-related news and classify them by variety.

    This is intentionally a broad, best-effort collector. It stores raw results in
    MarketSnapshot so report generation remains reproducible, but it does not
    block the daily report when a public source changes or rate-limits.
    """
    run = start_crawler_run(db, trade_date, "ALL", "news_digest", source=SOURCE)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if NEWS_SOURCES:
        workers = min(MAX_NEWS_WORKERS, len(NEWS_SOURCES))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_source_items, source): source for source in NEWS_SOURCES}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    items.extend(future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{source['name']}: {type(exc).__name__}: {exc}")
    items = dedupe_items(classify_items(items))[:MAX_NEWS_ITEMS]
    # Keep only latest same-day public news snapshot to avoid unbounded duplicates.
    # Delete before insert so the freshly added row is not removed by the same
    # transaction on SQLite.
    db.execute(
        delete(MarketSnapshot).where(
            MarketSnapshot.trade_date == trade_date,
            MarketSnapshot.exchange == "ALL",
            MarketSnapshot.source == SOURCE,
            MarketSnapshot.snapshot_type == "news_digest",
        )
    )
    db.add(MarketSnapshot(
        trade_date=trade_date,
        exchange="ALL",
        source=SOURCE,
        snapshot_type="news_digest",
        raw_json=json.dumps({"items": items, "viewpoints": build_news_viewpoints(items), "errors": errors}, ensure_ascii=False, default=str),
    ))
    db.flush()
    saved = len(items)
    error = "; ".join(errors) if errors and not saved else None
    finish_crawler_run(run, rows=len(items), saved=saved, error=error)
    update_data_gap(db, trade_date, "ALL", "news_digest", saved, error)
    db.commit()
    return {"trade_date": trade_date, "rows": len(items), "saved": saved, "error": error, "sources": [s["name"] for s in NEWS_SOURCES]}


def fetch_source_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    kind = source.get("kind")
    name = source["name"]
    url = source["url"]
    if kind == "eastmoney_search":
        out: list[dict[str, Any]] = []
        for query in source.get("queries") or []:
            out.extend(fetch_eastmoney_search(name, url, query))
        return out
    if kind == "sina_roll":
        return fetch_sina_roll(name, url)
    if kind == "quhe_kuaixun":
        return fetch_quhe_kuaixun(name, url)
    if kind == "article_links":
        return fetch_article_links(name, url)
    if kind == "article_links_gbk":
        return fetch_article_links(name, url, encoding="gbk")
    if kind == "cls_depth":
        return fetch_cls_depth(name, url)
    return []


def load_latest_news_digest(db: Session, trade_date: str) -> dict[str, Any]:
    rows = [
        s for s in db.query(MarketSnapshot)
        .filter(MarketSnapshot.trade_date == trade_date, MarketSnapshot.snapshot_type == "news_digest")
        .order_by(MarketSnapshot.created_at.desc())
        .limit(1)
    ]
    if not rows:
        return {"items": [], "summary": {}, "status": "missing"}
    try:
        raw = json.loads(rows[0].raw_json or "{}")
    except Exception:
        raw = {}
    items = raw.get("items") or []
    return {"items": items, "summary": summarize_news(items), "viewpoints": raw.get("viewpoints") or build_news_viewpoints(items), "status": "ok", "source": rows[0].source, "created_at": rows[0].created_at}


def fetch_eastmoney_search(source_name: str, url_template: str, query: str) -> list[dict[str, Any]]:
    param = {
        "uid": "",
        "keyword": query,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": 20}},
    }
    url = url_template.format(param=quote(json.dumps(param, ensure_ascii=False)))
    text = requests.get(url, headers={"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}, timeout=12).text
    m = re.search(r"\((\{.*\})\)\s*$", text, re.S)
    data = json.loads(m.group(1) if m else text)
    result = data.get("result") or {}
    cms = result.get("cmsArticleWebOld") if isinstance(result, dict) else {}
    if isinstance(cms, list):
        rows = cms
    elif isinstance(cms, dict):
        rows = cms.get("data") or cms.get("list") or []
    else:
        rows = []
    out = []
    for row in rows:
        title = clean_html(row.get("title") or row.get("mediaName") or "")
        if not title:
            continue
        out.append({
            "source": source_name,
            "title": title,
            "url": row.get("url") or row.get("link") or row.get("art_url") or "",
            "published_at": normalize_time(row.get("date") or row.get("showTime") or row.get("publishTime") or row.get("show_time")),
            "summary": clean_html(row.get("content") or row.get("summary") or row.get("digest") or ""),
            "query": query,
        })
    return out


def fetch_sina_roll(source_name: str, url: str) -> list[dict[str, Any]]:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn/futuremarket/"}, timeout=12)
    r.encoding = "utf-8"
    data = r.json()
    rows = ((data.get("result") or {}).get("data") or []) if isinstance(data, dict) else []
    out = []
    for row in rows:
        title = clean_html(row.get("title") or "")
        if not title:
            continue
        out.append({
            "source": source_name,
            "title": title,
            "url": row.get("url") or "",
            "published_at": normalize_time(row.get("ctime") or row.get("time") or row.get("date")),
            "summary": clean_html(row.get("intro") or ""),
        })
    return out

def _news_keywords() -> list[str]:
    return [
        "期货", "商品", "原油", "黄金", "白银", "铜", "铝", "锌", "镍", "锡", "钢", "螺纹", "铁矿", "焦煤", "焦炭",
        "农产品", "豆粕", "豆油", "棕榈", "鸡蛋", "生猪", "白糖", "棉花", "红枣", "能化", "PTA", "PX", "甲醇",
        "纯碱", "玻璃", "橡胶", "碳酸锂", "集运", "欧线", "国债期货", "股指期货", "涨停", "跌停", "涨", "跌",
        "持仓", "仓单", "库存", "基差", "现货", "进口", "出口", "供需", "宏观", "美元", "美联储", "OPEC", "EIA", "USDA",
    ]


def _abs_url(url: str, base: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        m = re.match(r"https?://[^/]+", base)
        return (m.group(0) if m else "") + url
    return url


def fetch_quhe_kuaixun(source_name: str, url: str) -> list[dict[str, Any]]:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://www.quheqihuo.com/"}, timeout=12)
    r.encoding = "utf-8"
    html = r.text
    out = []
    for time_s, title in re.findall(r'<span>(\d{2}:\d{2}:\d{2})</span>.*?<a[^>]+title=["\']([^"\']{10,})["\']', html, re.S):
        title = clean_html(unescape(title))
        if not title:
            continue
        out.append({"source": source_name, "title": title, "url": url, "published_at": f"{datetime.now():%Y-%m-%d} {time_s}", "summary": "曲合盘中快讯"})
        if len(out) >= 30:
            break
    return out


def fetch_article_links(source_name: str, url: str, encoding: str | None = None) -> list[dict[str, Any]]:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": url}, timeout=12)
    r.encoding = encoding or r.apparent_encoding or "utf-8"
    html = r.text
    keywords = _news_keywords()
    out: list[dict[str, Any]] = []
    seen = set()
    for href, raw_title in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S):
        title = clean_html(unescape(raw_title))
        if len(title) < 8:
            continue
        if any(bad in title for bad in ["微博", "开户", "登录", "注册", "广告", "投稿", "设为首页", "加入收藏", "${", "function", "undefined"]):
            continue
        text = title.upper()
        if not any(k.upper() in text for k in keywords):
            continue
        full_url = _abs_url(href, url)
        key = full_url or title
        if key in seen:
            continue
        seen.add(key)
        out.append({"source": source_name, "title": title[:180], "url": full_url, "published_at": "", "summary": f"{source_name}热点"})
        if len(out) >= 30:
            break
    return out


def fetch_cls_depth(source_name: str, url: str) -> list[dict[str, Any]]:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://www.cls.cn/", "Accept": "text/html"}, timeout=12)
    r.encoding = "utf-8"
    html = r.text
    idx = html.find('"assembleData"')
    if idx < 0:
        return []
    brace_start = html.find("{", idx + len('"assembleData":'))
    if brace_start < 0:
        return []
    depth = 0
    json_end = -1
    for i in range(brace_start, min(brace_start + 220000, len(html))):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break
    if json_end < 0:
        return []
    data = json.loads(html[brace_start:json_end])
    keywords = _news_keywords()
    out = []
    for row in (data.get("depth_list") or [])[:60]:
        title = clean_html(row.get("title") or "")
        if len(title) < 8:
            continue
        text = f"{title} {row.get('brief') or ''}".upper()
        if not any(k.upper() in text for k in keywords):
            continue
        article_id = row.get("id")
        ctime = row.get("ctime")
        out.append({
            "source": source_name,
            "title": title[:180],
            "url": f"https://www.cls.cn/detail/{article_id}" if article_id else url,
            "published_at": normalize_time(ctime),
            "summary": clean_html(row.get("brief") or row.get("source") or ""),
        })
        if len(out) >= 20:
            break
    return out


def classify_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keywords = build_keyword_index()
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".upper()
        matches = []
        for symbol, words in keywords.items():
            if any(word and word.upper() in text for word in words):
                matches.append(symbol)
        item["symbols"] = sorted(set(matches))[:8]
        item["sectors"] = sorted({sector_for_symbol(x) for x in item["symbols"] if sector_for_symbol(x)})
        item["importance"] = importance_score(item, text)
    items.sort(key=lambda x: (x.get("importance") or 0, x.get("published_at") or ""), reverse=True)
    return items


def build_keyword_index() -> dict[str, list[str]]:
    index = {}
    aliases = {
        "RB": ["螺纹", "钢材", "黑色"], "HC": ["热卷", "钢材"], "I": ["铁矿", "铁矿石"], "JM": ["焦煤"], "J": ["焦炭"],
        "CU": ["铜", "沪铜"], "AL": ["铝", "沪铝"], "ZN": ["锌", "沪锌"], "NI": ["镍", "沪镍"], "SN": ["锡", "沪锡"],
        "AU": ["黄金", "沪金"], "AG": ["白银", "沪银"], "SC": ["原油"], "FU": ["燃料油"], "LU": ["低硫燃料油"], "BU": ["沥青"],
        "TA": ["PTA"], "PX": ["PX", "对二甲苯"], "PF": ["短纤"], "EG": ["乙二醇"], "MA": ["甲醇"], "SA": ["纯碱"], "FG": ["玻璃"],
        "M": ["豆粕"], "Y": ["豆油"], "P": ["棕榈油", "棕榈"], "A": ["豆一", "大豆"], "C": ["玉米"], "JD": ["鸡蛋"], "LH": ["生猪"],
        "CF": ["棉花"], "SR": ["白糖"], "CJ": ["红枣"], "AP": ["苹果"], "RM": ["菜粕"], "OI": ["菜油"],
        "LC": ["碳酸锂"], "SI": ["工业硅"], "EC": ["集运", "欧线"], "RU": ["橡胶", "天然橡胶"], "BR": ["丁二烯橡胶"],
    }
    for sym, meta in VARIETY_META_BY_SYMBOL.items():
        index[sym] = sorted(set([sym, meta[0], meta[1], *aliases.get(sym, [])]))
    return index


def sector_for_symbol(symbol: str) -> str:
    sym = symbol.upper()
    if sym in {"RB", "HC", "I", "JM", "J", "SF", "SM"}: return "黑色"
    if sym in {"CU", "AL", "ZN", "PB", "NI", "SN", "SS", "AO", "BC", "LC", "SI"}: return "有色/新能源"
    if sym in {"AU", "AG"}: return "贵金属"
    if sym in {"SC", "FU", "LU", "BU", "TA", "PX", "PF", "EG", "EB", "MA", "SA", "FG", "UR", "L", "V", "PP", "RU", "BR", "NR"}: return "能化"
    if sym in {"M", "Y", "P", "A", "B", "C", "CS", "JD", "LH", "CF", "SR", "CJ", "AP", "RM", "OI", "PK"}: return "农产品"
    if sym in {"IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"}: return "金融"
    return "其他"


def importance_score(item: dict[str, Any], text: str) -> int:
    score = len(item.get("symbols") or []) * 2
    for kw in ["涨停", "跌停", "大涨", "大跌", "持仓", "仓单", "库存", "基差", "交割", "保证金", "政策", "进口", "出口", "供给", "需求"]:
        if kw in text:
            score += 3
    return score


def summarize_news(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, int] = {}
    by_sector: dict[str, int] = {}
    for item in items:
        for sym in item.get("symbols") or []:
            by_symbol[sym] = by_symbol.get(sym, 0) + 1
        for sector in item.get("sectors") or []:
            by_sector[sector] = by_sector.get(sector, 0) + 1
    return {
        "count": len(items),
        "top_symbols": sorted(by_symbol.items(), key=lambda x: x[1], reverse=True)[:10],
        "top_sectors": sorted(by_sector.items(), key=lambda x: x[1], reverse=True)[:8],
    }



def build_news_viewpoints(items: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    """Summarize public news into per-variety/sector reading notes.

    This is rule-based on purpose: deterministic, cheap, and safe for scheduled
    reports. Later an LLM can rewrite these notes, but the structured evidence
    should still come from here.
    """
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for sym in item.get("symbols") or []:
            by_symbol.setdefault(sym, []).append(item)
    viewpoints = []
    for sym, rows in by_symbol.items():
        rows = sorted(rows, key=lambda x: (x.get("importance") or 0, x.get("published_at") or ""), reverse=True)
        text = " ".join(f"{r.get('title','')} {r.get('summary','')}" for r in rows[:8])
        tags = extract_news_tags(text)
        bias, bias_reason = infer_news_bias(text, tags)
        drivers = top_driver_phrases(text)
        viewpoints.append({
            "symbol": sym,
            "name": VARIETY_META_BY_SYMBOL.get(sym, (sym,))[0],
            "sector": sector_for_symbol(sym),
            "news_count": len(rows),
            "bias": bias,
            "bias_reason": bias_reason,
            "tags": tags,
            "drivers": drivers,
            "summary": build_viewpoint_summary(sym, rows, bias, tags, drivers),
            "top_news": [{"title": r.get("title"), "url": r.get("url"), "source": r.get("source"), "published_at": r.get("published_at")} for r in rows[:3]],
        })
    viewpoints.sort(key=lambda x: (x["news_count"], len(x["tags"]), x["bias"] != "neutral"), reverse=True)
    return viewpoints[:limit]


def extract_news_tags(text: str) -> list[str]:
    groups = {
        "供给": ["供应", "供给", "产量", "减产", "停产", "复产", "检修", "开工", "进口", "出口", "到港"],
        "需求": ["需求", "消费", "成交", "补库", "去库", "订单", "表需", "终端"],
        "库存/仓单": ["库存", "仓单", "库容", "累库", "去库"],
        "政策": ["政策", "监管", "关税", "反倾销", "配额", "会议", "通知", "公告"],
        "宏观": ["美元", "利率", "美联储", "CPI", "非农", "通胀", "汇率", "避险"],
        "资金/持仓": ["持仓", "资金", "净多", "净空", "增仓", "减仓", "主力"],
        "海外": ["美国", "巴西", "阿根廷", "欧佩克", "OPEC", "EIA", "USDA", "伦敦", "外盘"],
        "天气": ["天气", "降雨", "干旱", "洪水", "种植", "收割"],
        "价格异动": ["涨停", "跌停", "大涨", "大跌", "拉升", "跳水", "新高", "新低"],
    }
    tags = []
    for tag, words in groups.items():
        if any(w.upper() in text.upper() for w in words):
            tags.append(tag)
    return tags


def infer_news_bias(text: str, tags: list[str]) -> tuple[str, str]:
    t = text.upper()
    positive_words = ["上涨", "涨超", "大涨", "拉升", "偏强", "支撑", "收紧", "去库", "减产", "供应紧张", "需求改善", "反弹"]
    negative_words = ["下跌", "跌超", "大跌", "跳水", "偏弱", "承压", "累库", "增产", "供应增加", "需求疲弱", "回落"]
    pos = sum(t.count(w.upper()) for w in positive_words)
    neg = sum(t.count(w.upper()) for w in negative_words)
    if pos >= neg + 2:
        return "positive", f"偏多词频 {pos} 高于偏空词频 {neg}"
    if neg >= pos + 2:
        return "negative", f"偏空词频 {neg} 高于偏多词频 {pos}"
    if pos or neg:
        return "mixed", f"多空词频接近：偏多 {pos} / 偏空 {neg}"
    if tags:
        return "neutral", "资讯集中在" + "、".join(tags[:3])
    return "neutral", "暂无明确方向词"


def top_driver_phrases(text: str) -> list[str]:
    drivers = []
    mapping = [
        ("库存", "库存/仓单变化"), ("仓单", "库存/仓单变化"), ("持仓", "资金持仓变化"), ("资金", "资金持仓变化"),
        ("进口", "进口/到港变化"), ("到港", "进口/到港变化"), ("出口", "出口变化"),
        ("需求", "需求变化"), ("供应", "供应变化"), ("供给", "供应变化"), ("减产", "供应收缩"),
        ("美联储", "海外宏观"), ("美元", "海外宏观"), ("EIA", "能源库存事件"), ("USDA", "农产品报告"),
        ("政策", "政策扰动"), ("关税", "政策扰动"), ("天气", "天气扰动"),
    ]
    up = text.upper()
    for kw, label in mapping:
        if kw.upper() in up and label not in drivers:
            drivers.append(label)
    return drivers[:5]


def build_viewpoint_summary(sym: str, rows: list[dict[str, Any]], bias: str, tags: list[str], drivers: list[str]) -> str:
    name = VARIETY_META_BY_SYMBOL.get(sym, (sym,))[0]
    bias_text = {"positive": "偏多", "negative": "偏空", "mixed": "分歧", "neutral": "中性"}.get(bias, "中性")
    topic = "、".join(drivers[:3] or tags[:3] or ["资讯热度"])
    title = rows[0].get("title") if rows else ""
    return f"{name}资讯热度 {len(rows)} 条，方向暂判{bias_text}，主要围绕{topic}；代表资讯：{title}"

def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = item.get("url") or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def clean_html(text: Any) -> str:
    text = str(text or "")
    text = re.sub(r"<.*?>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        try:
            # Sina ctime is usually seconds.
            return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)
    text = str(value)
    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return text
