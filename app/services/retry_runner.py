from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import JobRun
from app.services.collector import collect_daily_market, collect_seat_ranks
from app.services.coverage_diff import diff_coverage_matrix
from app.services.coverage_matrix import build_coverage_matrix
from app.services.data_mart import materialize_variety_dataset
from app.services.quhe_collector import collect_quhe_enhancements
from app.services.report_builder import build_report
from app.services.retry_planner import build_retry_plan


def run_retry_plan(db: Session, trade_date: str, *, max_steps: int = 3, stop_on_failure: bool = False, rebuild: bool = True) -> dict[str, Any]:
    """Execute the retry planner sequentially with per-step coverage diffs.

    This runner is intentionally conservative: it executes only known safe step
    types emitted by the planner, records before/after coverage for every step,
    and never invents data when a source remains unavailable.
    """
    plan = build_retry_plan(db, trade_date)
    steps = (plan.get("steps") or [])[: max(0, int(max_steps or 0))]
    job = JobRun(
        name="retry_plan",
        status="running",
        trade_date=trade_date,
        started_at=datetime.utcnow(),
        message=f"max_steps={max_steps} stop_on_failure={stop_on_failure}",
    )
    db.add(job)
    db.commit()

    executed: list[dict[str, Any]] = []
    try:
        for step in steps:
            result = run_retry_step(db, trade_date, step, rebuild=rebuild)
            executed.append(result)
            if stop_on_failure and result.get("status") == "failed":
                break

        finalization = finalize_retry_run(db, trade_date, rebuild=rebuild)
        after_plan = build_retry_plan(db, trade_date)
        failures = [x for x in executed if x.get("status") == "failed"]
        improvements = sum(int((x.get("coverage_diff") or {}).get("improved_cells") or 0) for x in executed)
        job.status = retry_job_status(executed, failures, finalization)
        job.message = runner_summary(executed, improvements, failures, finalization)
        job.result_json = json.dumps({"initial_plan": plan, "executed": executed, "finalization": finalization, "after_plan": after_plan}, ensure_ascii=False, default=str)
        job.finished_at = datetime.utcnow()
        db.commit()
        return {
            "ok": not failures,
            "trade_date": trade_date,
            "job_id": job.id,
            "job_status": job.status,
            "summary": job.message,
            "initial_plan": plan,
            "executed": executed,
            "after_plan": after_plan,
            "finalization": finalization,
        }
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.message = f"{type(exc).__name__}: {exc}"
        job.result_json = json.dumps({"initial_plan": plan, "executed": executed, "error": job.message}, ensure_ascii=False, default=str)
        job.finished_at = datetime.utcnow()
        db.commit()
        raise


def run_retry_step(db: Session, trade_date: str, step: dict[str, Any], *, rebuild: bool = True) -> dict[str, Any]:
    before = build_coverage_matrix(db, trade_date, sync_gaps=False)
    started_at = datetime.utcnow()
    status = "success"
    error = ""
    payload: dict[str, Any] | None = None
    try:
        if step.get("type") == "recollect":
            exchange = step.get("exchange")
            kind = step.get("kind")
            if kind == "daily":
                payload = {"collect": collect_daily_market(db, trade_date, exchanges=[exchange])}
            elif kind == "seat_rank":
                payload = {"seats": collect_seat_ranks(db, trade_date, exchanges=[exchange])}
            else:
                raise ValueError(f"unsupported recollect kind: {kind}")
            if rebuild:
                report = build_report(db, trade_date)
                payload["report"] = {"score": report.score, "summary": report.summary}
        elif step.get("type") == "collect_quhe":
            collect = collect_quhe_enhancements(db, trade_date)
            materialized = materialize_variety_dataset(db, trade_date)
            payload = {"collect": collect, "materialized": materialized}
            if rebuild:
                report = build_report(db, trade_date)
                payload["report"] = {"score": report.score, "summary": report.summary}
        else:
            raise ValueError(f"unsupported retry step type: {step.get('type')}")
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    after = build_coverage_matrix(db, trade_date, sync_gaps=True)
    coverage_diff = diff_coverage_matrix(before, after)
    return {
        "step": step,
        "status": status,
        "error": error,
        "started_at": started_at,
        "finished_at": datetime.utcnow(),
        "coverage_diff": coverage_diff,
        "result": payload,
        "summary": coverage_diff.get("summary") or ("执行失败" if status == "failed" else "执行完成"),
    }


def finalize_retry_run(db: Session, trade_date: str, *, rebuild: bool = True) -> dict[str, Any]:
    """Always close a retry run with materialization, quality, and report state.

    The runner may execute zero steps or every step may fail. Even then the UI
    needs a deterministic answer: did we have enough data for a real report, or
    did we create a blocked/no-data report that explains why not?
    """
    before = build_coverage_matrix(db, trade_date, sync_gaps=False)
    materialized = materialize_variety_dataset(db, trade_date)
    after_materialize = build_coverage_matrix(db, trade_date, sync_gaps=True)
    report_payload: dict[str, Any] | None = None
    if rebuild:
        report = build_report(db, trade_date)
        report_payload = {"status": report.status, "score": report.score, "summary": report.summary}
    after_report = build_coverage_matrix(db, trade_date, sync_gaps=False)
    return {
        "materialized": materialized,
        "coverage_diff": diff_coverage_matrix(before, after_materialize),
        "coverage_matrix": after_report,
        "report": report_payload,
        "status": "blocked" if report_payload and report_payload.get("status") == "blocked" else "success",
    }


def retry_job_status(executed: list[dict[str, Any]], failures: list[dict[str, Any]], finalization: dict[str, Any]) -> str:
    if finalization.get("status") == "blocked":
        return "partial" if executed else "failed"
    if failures and not any(x.get("status") == "success" for x in executed):
        return "failed"
    if failures:
        return "partial"
    return "success"


def runner_summary(executed: list[dict[str, Any]], improvements: int, failures: list[dict[str, Any]], finalization: dict[str, Any] | None = None) -> str:
    finalization = finalization or {}
    if not executed:
        base = "没有可执行的补采步骤。"
    else:
        parts = [f"执行 {len(executed)} 步", f"改善 {improvements} 项"]
        if failures:
            parts.append(f"失败 {len(failures)} 步")
        base = "；".join(parts)
    report = finalization.get("report") or {}
    if report.get("status") == "blocked":
        return f"{base}；日报未生成有效结论：{report.get('summary') or '缺少可用行情数据'}"
    if report:
        return f"{base}；已重建日报：{report.get('summary') or '-'}"
    return base
