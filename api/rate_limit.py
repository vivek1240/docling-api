"""
Rate Limiting
=============

Implements rate limiting using slowapi with optional Redis backend.
"""

from typing import Optional
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import get_settings


def _get_key_func(request: Request) -> str:
    """
    Get rate limit key from API key or IP address.
    
    Prioritizes API key for per-key rate limiting,
    falls back to IP address for unauthenticated requests.
    """
    # Try to get API key from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
        # Use first part of key (the ID) for rate limiting
        if "_" in api_key:
            return f"key:{api_key.split('_')[0]}_{api_key.split('_')[1]}"
        return f"key:{api_key[:20]}"
    
    # Fall back to IP address
    return f"ip:{get_remote_address(request)}"


def create_limiter() -> Limiter:
    """Create and configure the rate limiter."""
    settings = get_settings()
    
    # Use Redis if available and not localhost, otherwise in-memory
    # In cloud deployments, localhost Redis won't work
    storage_uri = "memory://"
    if settings.redis_url and "localhost" not in settings.redis_url and "127.0.0.1" not in settings.redis_url:
        storage_uri = settings.redis_url
    
    return Limiter(
        key_func=_get_key_func,
        default_limits=[f"{settings.rate_limit_requests_per_minute}/minute"],
        storage_uri=storage_uri,
        strategy="fixed-window",
        enabled=settings.rate_limit_enabled,
    )


# Global limiter instance
limiter = create_limiter()


def get_rate_limit_string() -> str:
    """Get the rate limit string for use in decorators."""
    settings = get_settings()
    return f"{settings.rate_limit_requests_per_minute}/minute"
