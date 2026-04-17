"""Liveness endpoint. Intentionally does not touch the DB — we want it green even
when the DB is in a bad state, so alerting can distinguish app-down from DB-down.
A /ready endpoint that asserts DB connectivity lands alongside the first real
tenant-scoped routes in Phase 1.
"""

from __future__ import annotations

from fastapi import APIRouter

from helm import __version__
from helm.config import get_settings

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "helm-api",
        "version": __version__,
        "env": settings.env,
    }
