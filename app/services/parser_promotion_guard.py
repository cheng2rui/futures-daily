from __future__ import annotations

from typing import Any

DEFAULT_THRESHOLDS = {
    "min_parsed_rows": 5,
    "min_success_rate": 70.0,
    "max_error_rate": 30.0,
    "required_mapping_keys": ["rank", "party"],
    "any_value_keys": ["vol", "long_open_interest", "short_open_interest"],
}


def evaluate_parser_promotion(parser_dry_run: dict[str, Any] | None, *, thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate whether a parser dry-run is safe enough for future promotion."""
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if not isinstance(parser_dry_run, dict):
        return blocked("no_parser_dry_run", "缺少 parser_dry_run，禁止提升。", cfg, [])

    results = parser_dry_run.get("results") if isinstance(parser_dry_run.get("results"), list) else [parser_dry_run]
    parsed_rows = sum(int(r.get("parsed_rows") or 0) for r in results if isinstance(r, dict))
    input_rows = sum(int(r.get("input_rows") or 0) for r in results if isinstance(r, dict))
    error_count = sum(int(r.get("error_count") or 0) for r in results if isinstance(r, dict))
    success_rate = round(parsed_rows / input_rows * 100, 1) if input_rows else 0.0
    error_rate = round(error_count / max(1, input_rows) * 100, 1)
    best_mapping = best_result_mapping(results)
    reasons: list[dict[str, Any]] = []

    if parsed_rows < int(cfg["min_parsed_rows"]):
        reasons.append({"code": "too_few_rows", "message": f"解析行数 {parsed_rows} 低于门槛 {cfg['min_parsed_rows']}。"})
    if success_rate < float(cfg["min_success_rate"]):
        reasons.append({"code": "low_success_rate", "message": f"成功率 {success_rate}% 低于门槛 {cfg['min_success_rate']}%。"})
    if error_rate > float(cfg["max_error_rate"]):
        reasons.append({"code": "high_error_rate", "message": f"错误率 {error_rate}% 高于门槛 {cfg['max_error_rate']}%。"})

    missing_required = [k for k in cfg["required_mapping_keys"] if k not in best_mapping]
    if missing_required:
        reasons.append({"code": "missing_required_mapping", "message": f"缺少必要列映射：{', '.join(missing_required)}。"})
    if not any(k in best_mapping for k in cfg["any_value_keys"]):
        reasons.append({"code": "missing_value_mapping", "message": f"缺少至少一个数值列映射：{', '.join(cfg['any_value_keys'])}。"})

    allowed = not reasons
    return {
        "allowed": allowed,
        "decision": "allow_promotion" if allowed else "block_promotion",
        "status": "pass" if allowed else "blocked",
        "summary": "parser dry-run 达到最低提升门槛。" if allowed else "parser dry-run 未达到提升门槛，禁止入库。",
        "metrics": {"input_rows": input_rows, "parsed_rows": parsed_rows, "error_count": error_count, "success_rate": success_rate, "error_rate": error_rate},
        "mapping": best_mapping,
        "thresholds": cfg,
        "reasons": reasons,
        "next_action": "可进入人工复核/受控入库流程。" if allowed else "继续调 parser 或改用 Excel/授权源；不要写入 seat_rank_rows。",
    }


def blocked(code: str, message: str, thresholds: dict[str, Any], reasons: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "allowed": False,
        "decision": "block_promotion",
        "status": "blocked",
        "summary": message,
        "metrics": {"input_rows": 0, "parsed_rows": 0, "error_count": 0, "success_rate": 0.0, "error_rate": 0.0},
        "mapping": {},
        "thresholds": thresholds,
        "reasons": reasons or [{"code": code, "message": message}],
        "next_action": "先完成 parser dry-run，再重新评估。",
    }


def best_result_mapping(results: list[Any]) -> dict[str, Any]:
    best = {}
    best_score = -1
    for r in results:
        if not isinstance(r, dict):
            continue
        mapping = r.get("mapping") if isinstance(r.get("mapping"), dict) else {}
        score = int(r.get("parsed_rows") or 0) * 10 + len(mapping)
        if score > best_score:
            best_score = score
            best = mapping
    return best
