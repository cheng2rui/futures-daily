from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MarketSnapshot


def build_data_quality(db: Session, trade_date: str) -> dict:
    expected = get_settings().exchanges.enabled
    snapshots = list(db.scalars(
        select(MarketSnapshot)
        .where(MarketSnapshot.trade_date == trade_date)
        .order_by(desc(MarketSnapshot.created_at))
    ))
    latest: dict[tuple[str, str], MarketSnapshot] = {}
    for snap in snapshots:
        latest.setdefault((snap.exchange, snap.snapshot_type), snap)

    rows = []
    available_count = 0
    ok_count = 0
    partial_count = 0
    for exchange in expected:
        daily = _snap_status(latest.get((exchange, 'daily')))
        seat = _snap_status(latest.get((exchange, 'seat_rank')))
        if daily['rows'] > 0:
            available_count += 1
        if daily['ok']:
            ok_count += 1
        elif daily['rows'] > 0:
            partial_count += 1
        rows.append({
            'exchange': exchange,
            'daily': daily,
            'seat_rank': seat,
            'status': 'ok' if daily['ok'] else 'partial' if daily['rows'] > 0 else 'failed',
        })

    total = len(expected)
    status = 'ok' if ok_count == total else 'partial' if available_count else 'failed'
    return {
        'trade_date': trade_date,
        'status': status,
        'daily_ok': ok_count,
        'daily_available': available_count,
        'expected': total,
        'coverage_pct': round(available_count / total * 100, 1) if total else 0,
        'exchanges': rows,
    }


def _snap_status(snap: MarketSnapshot | None) -> dict:
    if not snap:
        return {'ok': False, 'rows': 0, 'error': 'not_collected'}
    try:
        payload = json.loads(snap.raw_json or '{}')
    except Exception:
        payload = {}
    rows = payload.get('row_count')
    if rows is None:
        rows = len(payload.get('rows') or [])
    error = payload.get('error')
    return {'ok': bool(rows) and not error, 'rows': rows or 0, 'error': error}
