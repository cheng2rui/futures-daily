from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import JobRun

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.scalars(select(JobRun).order_by(desc(JobRun.started_at)).limit(limit)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "trade_date": r.trade_date,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "message": r.message,
            "result_json": r.result_json,
        }
        for r in rows
    ]
