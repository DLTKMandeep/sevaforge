"""
SevaForge API — Health & Status Endpoints
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from sevaforge.config import get_settings
from sevaforge.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """
    Health check endpoint.

    Returns server status, version, environment, and uptime.
    Used by load balancers, k8s probes, and monitoring.
    """
    settings = get_settings()
    start_time = getattr(request.app.state, "start_time", time.time())

    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=round(time.time() - start_time, 2),
    )


@router.get("/health/ready")
async def readiness_check(request: Request) -> dict:
    """
    Readiness probe — checks if the gateway is initialized.
    Returns 200 when ready, 503 if still starting up.
    """
    from sevaforge.api.app import get_gateway

    try:
        gateway = get_gateway()
        return {
            "ready": True,
            "cache_enabled": gateway.cache.enabled,
            "templates_loaded": len(gateway.prompt_engine.list_templates()),
        }
    except Exception:
        return {"ready": False, "reason": "Gateway not initialized"}
