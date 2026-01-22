"""
Health Check Endpoints
======================

Provides health and status endpoints for monitoring.
"""

from datetime import datetime
from fastapi import APIRouter, Response

from api.config import get_settings
from api.models.schemas import HealthResponse
from api.services.docling_client import get_docling_client


router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check the health status of the API and backend services.",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns the health status of:
    - This API service
    - The Docling backend
    """
    settings = get_settings()
    client = get_docling_client()
    
    # Check backend health
    backend_health = await client.health_check()
    
    return HealthResponse(
        status="healthy" if backend_health["status"] == "healthy" else "degraded",
        version=settings.api_version,
        docling_backend=backend_health["status"],
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/",
    summary="Root",
    description="API root endpoint with basic information.",
)
async def root():
    """Root endpoint with API information."""
    settings = get_settings()
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
    }


@router.get(
    "/ready",
    summary="Readiness Check",
    description="Kubernetes-style readiness probe.",
)
async def readiness_check(response: Response):
    """
    Readiness check for container orchestration.
    
    Returns 200 if ready to accept traffic, 503 otherwise.
    """
    client = get_docling_client()
    backend_health = await client.health_check()
    
    if backend_health["status"] != "healthy":
        response.status_code = 503
        return {"status": "not_ready", "reason": "backend_unhealthy"}
    
    return {"status": "ready"}


@router.get(
    "/live",
    summary="Liveness Check",
    description="Kubernetes-style liveness probe.",
)
async def liveness_check():
    """
    Liveness check for container orchestration.
    
    Returns 200 if the service is alive.
    """
    return {"status": "alive"}
