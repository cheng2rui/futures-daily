from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SourceFile

DEFAULT_ARCHIVE_ROOT = "data/raw_archive"


def archive_payload(
    db: Session,
    *,
    trade_date: str,
    exchange: str,
    kind: str,
    source: str,
    payload: Any,
    rows: int | None = None,
    error: str | None = None,
    content_type: str = "application/json",
) -> SourceFile:
    """Persist one raw source response to disk and index it in source_files.

    The archive is append-only by filename timestamp/hash. It intentionally stores
    the vendor-shaped payload before normalization so future parser fixes can
    replay historical responses without refetching remote sources.
    """
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    now = datetime.utcnow()
    root = Path(os.getenv("FUTURES_DAILY_RAW_ARCHIVE", DEFAULT_ARCHIVE_ROOT))
    folder = root / safe_part(trade_date) / safe_part(source) / safe_part(exchange)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%H%M%S_%f')}_{safe_part(kind)}_{digest[:10]}.json"
    path = folder / filename
    path.write_bytes(raw)

    row = SourceFile(
        trade_date=trade_date,
        exchange=exchange,
        kind=kind,
        source=source,
        path=str(path),
        content_type=content_type,
        rows=int(rows if rows is not None else infer_rows(payload)),
        size_bytes=len(raw),
        sha256=digest,
        error=error or "",
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def archive_fetch_result(db: Session, *, trade_date: str, exchange: str, kind: str, source: str, result: Any) -> SourceFile:
    rows = list(getattr(result, "rows", []) or [])
    payload = {
        "trade_date": trade_date,
        "exchange": exchange,
        "kind": kind,
        "source": source,
        "rows": rows,
        "row_count": len(rows),
        "error": getattr(result, "error", None),
        "meta": getattr(result, "meta", None),
    }
    return archive_payload(
        db,
        trade_date=trade_date,
        exchange=exchange,
        kind=kind,
        source=source,
        payload=payload,
        rows=len(rows),
        error=getattr(result, "error", None),
    )


def list_archives(db: Session, trade_date: str | None = None, exchange: str | None = None, kind: str | None = None, limit: int = 100) -> list[SourceFile]:
    stmt = select(SourceFile).order_by(desc(SourceFile.created_at)).limit(limit)
    if trade_date:
        stmt = stmt.where(SourceFile.trade_date == trade_date)
    if exchange:
        stmt = stmt.where(SourceFile.exchange == exchange.upper())
    if kind:
        stmt = stmt.where(SourceFile.kind == kind)
    return list(db.scalars(stmt).all())


def read_archive(file: SourceFile, max_chars: int = 200_000) -> dict[str, Any]:
    path = Path(file.path)
    exists = path.exists()
    text = path.read_text(encoding="utf-8")[:max_chars] if exists else ""
    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    return {
        "file": source_file_item(file),
        "exists": exists,
        "truncated": exists and path.stat().st_size > max_chars,
        "payload": parsed if parsed is not None else text,
    }


def source_file_item(row: SourceFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "trade_date": row.trade_date,
        "exchange": row.exchange,
        "kind": row.kind,
        "source": row.source,
        "path": row.path,
        "content_type": row.content_type,
        "rows": row.rows,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "error": row.error,
        "created_at": row.created_at,
    }


def infer_rows(payload: Any) -> int:
    if isinstance(payload, dict):
        if isinstance(payload.get("row_count"), int):
            return payload["row_count"]
        rows = payload.get("rows")
        if isinstance(rows, list):
            return len(rows)
    if isinstance(payload, list):
        return len(payload)
    return 0


def safe_part(value: str) -> str:
    text = str(value or "unknown").strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:80] or "unknown"
