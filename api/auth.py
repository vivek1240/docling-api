"""
API Key Authentication
======================

Handles API key validation and authentication using database persistence.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.db_models import APIKey
from api.services.key_service import APIKeyService


# Security schemes
security = HTTPBearer(
    scheme_name="API Key",
    description="API key authentication. Use your API key as the Bearer token.",
)

# Optional security (doesn't raise error if missing)
optional_security = HTTPBearer(
    scheme_name="API Key (Optional)",
    description="Optional API key authentication.",
    auto_error=False,
)


# =============================================================================
# FastAPI Dependencies
# =============================================================================

async def get_key_service(db: AsyncSession = Depends(get_db)) -> APIKeyService:
    """Get API key service instance."""
    return APIKeyService(db)


async def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    key_service: APIKeyService = Depends(get_key_service),
) -> tuple[APIKey, str]:
    """
    FastAPI dependency to validate API key from Authorization header.
    
    Returns:
        Tuple of (APIKey model, raw_key string)
    
    Usage:
        @app.get("/protected")
        async def protected_route(auth: tuple = Depends(get_current_api_key)):
            api_key, raw_key = auth
            ...
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    raw_key = credentials.credentials
    api_key = await key_service.validate_key(raw_key)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if api_key.credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credits. Please add more credits to continue.",
        )
    
    return api_key, raw_key


async def get_optional_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security),
    db: AsyncSession = Depends(get_db),
) -> Optional[tuple[APIKey, str]]:
    """
    Optional API key authentication - doesn't raise if missing.
    
    Useful for endpoints that work with or without auth.
    """
    if not credentials:
        return None
    
    key_service = APIKeyService(db)
    raw_key = credentials.credentials
    api_key = await key_service.validate_key(raw_key)
    
    if api_key:
        return api_key, raw_key
    
    return None


# =============================================================================
# Helper Functions
# =============================================================================

def api_key_to_dict(api_key: APIKey) -> Dict[str, Any]:
    """Convert APIKey model to dictionary for responses."""
    return {
        "id": api_key.key_id,
        "name": api_key.name,
        "tier": api_key.tier,
        "credits": api_key.credits,
        "credits_used": api_key.credits_used,
        "documents_processed": api_key.documents_processed,
        "pages_processed": api_key.pages_processed,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at,
        "last_used": api_key.last_used,
    }
