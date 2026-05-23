from __future__ import annotations

from fastapi import APIRouter

from app.sources.registry import list_provider_capabilities

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources():
    return {"providers": list_provider_capabilities()}
