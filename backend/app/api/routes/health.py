"""Health endpoints."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Liveness: the process is up. Does not touch external dependencies."""
    settings = request.app.state.settings
    return {"status": "ok", "version": __version__, "env": settings.app_env}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: dependencies needed to serve traffic are reachable."""
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed: database unreachable")
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "up"})
