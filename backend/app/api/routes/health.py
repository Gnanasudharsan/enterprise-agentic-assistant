"""Health endpoints."""

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Liveness: the process is up. Does not touch external dependencies."""
    settings = request.app.state.settings
    return {"status": "ok", "version": __version__, "env": settings.app_env}
