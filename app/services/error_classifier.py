from __future__ import annotations

import re
from typing import Any


class ErrorCategory(dict):
    pass


CATEGORY_RULES: list[tuple[str, str, str, str, str]] = [
    ("anti_bot", r"\b(412|403|429)\b|challenge|cloudflare|captcha|forbidden|访问过于频繁|反爬|验证", "反爬/访问限制", "目标站点触发挑战、频控或拒绝访问。", "降低频率，保留 raw archive；优先尝试官方可下载文件、浏览器会话、FlareSolverr 或授权源。"),
    ("timeout", r"timeout|timed out|read timed|connect timed|超时|etimedout", "网络超时", "请求超时或连接不稳定。", "重试并增加 timeout；若连续发生，检查网络、DNS、代理和源站可用性。"),
    ("network", r"connection|connreset|dns|name resolution|network|proxy|ssl|certificate|连接失败|网络|证书", "网络/连接错误", "网络连接、DNS、代理或 TLS 证书异常。", "检查网络出口、代理、DNS 和证书；必要时切备用源。"),
    ("empty", r"empty|no data|0 rows|zero rows|暂无数据|空返回|为空|无数据", "源返回为空", "数据源请求成功但没有返回可入库数据。", "确认当日是否有披露；若应有数据，检查参数、交易日和品种映射。"),
    ("parser", r"parse|parser|jsondecode|decode|schema|field|column|keyerror|valueerror|解析|字段|格式", "解析/字段格式异常", "源返回结构与 parser 预期不一致。", "用 raw archive 做 parser replay，对比字段变更后修 parser。"),
    ("adapter_not_supported", r"not supported|unsupported|adapter 未实现|暂无公开 adapter|不适用|未实现", "Adapter 未支持", "当前 adapter 尚未覆盖该交易所或数据类型。", "先接 raw archive 保存原始响应，再补 adapter/parser；或接入授权数据源。"),
    ("auth", r"unauthorized|401|token|apikey|api key|permission|鉴权|授权|权限", "鉴权/权限问题", "数据源需要有效凭证或当前账号无权限。", "检查 token/API key/额度和授权范围。"),
]

DEFAULT_CATEGORY = {
    "code": "unknown",
    "label": "未知错误",
    "reason": "错误信息不足，暂时无法归因。",
    "suggestion": "查看 latest_run、raw archive 和服务日志，必要时增加更明确的错误记录。",
}


def classify_error(error: str | None, *, status: str | None = None, kind: str | None = None, source: str | None = None) -> dict[str, Any]:
    text = str(error or "").strip()
    if not text and status in {"missing", "failed"}:
        return {
            **DEFAULT_CATEGORY,
            "code": "missing_without_error",
            "label": "缺失但无错误详情",
            "reason": "覆盖矩阵显示缺失或失败，但采集记录没有保存具体错误。",
            "suggestion": "下次采集时记录源响应、HTTP 状态码和异常栈摘要。",
            "raw": text,
            "source": source or "",
            "kind": kind or "",
        }
    if not text:
        return {**DEFAULT_CATEGORY, "raw": "", "source": source or "", "kind": kind or ""}

    lowered = text.lower()
    for code, pattern, label, reason, suggestion in CATEGORY_RULES:
        if re.search(pattern, lowered, re.IGNORECASE):
            return {
                "code": code,
                "label": label,
                "reason": reason,
                "suggestion": suggestion,
                "raw": text,
                "source": source or "",
                "kind": kind or "",
            }
    return {**DEFAULT_CATEGORY, "raw": text, "source": source or "", "kind": kind or ""}


def classify_record_error(*, error: str | None = None, message: str | None = None, status: str | None = None, kind: str | None = None, source: str | None = None) -> dict[str, Any]:
    raw = error or message or ""
    return classify_error(raw, status=status, kind=kind, source=source)


def summarize_categories(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for item in items:
        category = item.get("error_category") if isinstance(item.get("error_category"), dict) else item
        code = str(category.get("code") or "unknown")
        counts[code] = counts.get(code, 0) + 1
        labels[code] = str(category.get("label") or code)
    actionable = {k: v for k, v in counts.items() if k not in {"unknown", "missing_without_error"}}
    top_pool = actionable or counts
    top_code = max(top_pool, key=top_pool.get) if top_pool else ""
    unknown_count = counts.get("unknown", 0) + counts.get("missing_without_error", 0)
    suffix = f"；另有 {unknown_count} 项缺少错误详情" if top_code and unknown_count and actionable else ""
    return {
        "counts": counts,
        "top_code": top_code,
        "top_label": labels.get(top_code, ""),
        "unknown_count": unknown_count,
        "summary": f"主要原因：{labels.get(top_code)}（{counts[top_code]} 项）{suffix}" if top_code else "暂无失败归因。",
    }
