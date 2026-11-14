"""Liveness and readiness probes."""

from typing import Any

from fastapi import APIRouter, Response, status

from seo_agent.observability.logging import get_logger
from seo_agent.persistence.database import ping

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


@router.get("/live")
async def live() -> dict[str, str]:
    """The process is up. Touches no dependencies."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict[str, Any]:
    """The database is reachable. Returns 503 otherwise."""
    try:
        await ping()
    except Exception as exc:
        logger.warning("readiness_check_failed", error=type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "checks": {"database": "unavailable"}}
    return {"status": "ok", "checks": {"database": "ok"}}
