"""
API Key Management Endpoints
============================

Endpoints for creating and managing API keys with database persistence.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.auth import get_current_api_key, get_key_service
from api.services.key_service import APIKeyService
from api.models.db_models import APIKey
from api.models.schemas import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyUsage,
    PricingTier,
)


router = APIRouter(prefix="/v1/keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API Key",
    description="Create a new API key. The key is only shown once.",
)
async def create_key(
    body: APIKeyCreate,
    key_service: APIKeyService = Depends(get_key_service),
) -> APIKeyResponse:
    """
    Create a new API key.
    
    **Important**: The API key value is only returned once upon creation.
    Store it securely - it cannot be retrieved later.
    """
    api_key, full_key = await key_service.create_key(
        name=body.name,
        tier=body.tier.value,
        credits=body.credits,
    )
    
    return APIKeyResponse(
        id=api_key.key_id,
        key=full_key,
        name=api_key.name,
        tier=PricingTier(api_key.tier),
        credits=api_key.credits,
        created_at=api_key.created_at,
        is_active=api_key.is_active,
    )


@router.get(
    "/me",
    response_model=APIKeyUsage,
    summary="Get Current Key Usage",
    description="Get usage information for the current API key.",
)
async def get_current_usage(
    auth: tuple = Depends(get_current_api_key),
) -> APIKeyUsage:
    """
    Get usage information for the currently authenticated API key.
    """
    api_key, _ = auth
    
    return APIKeyUsage(
        key_id=api_key.key_id,
        name=api_key.name,
        tier=PricingTier(api_key.tier),
        credits_remaining=api_key.credits,
        credits_used=api_key.credits_used,
        documents_processed=api_key.documents_processed,
        pages_processed=api_key.pages_processed,
        last_used=api_key.last_used,
    )


@router.get(
    "/{key_id}",
    response_model=APIKeyUsage,
    summary="Get Key Details",
    description="Get details for a specific API key by ID.",
)
async def get_key_details(
    key_id: str,
    key_service: APIKeyService = Depends(get_key_service),
) -> APIKeyUsage:
    """
    Get details for a specific API key.
    
    Note: This endpoint should be protected by admin auth in production.
    """
    api_key = await key_service.get_by_id(key_id)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )
    
    return APIKeyUsage(
        key_id=api_key.key_id,
        name=api_key.name,
        tier=PricingTier(api_key.tier),
        credits_remaining=api_key.credits,
        credits_used=api_key.credits_used,
        documents_processed=api_key.documents_processed,
        pages_processed=api_key.pages_processed,
        last_used=api_key.last_used,
    )


@router.post(
    "/{key_id}/credits",
    response_model=APIKeyUsage,
    summary="Add Credits",
    description="Add credits to an API key.",
)
async def add_key_credits(
    key_id: str,
    credits: int,
    key_service: APIKeyService = Depends(get_key_service),
) -> APIKeyUsage:
    """
    Add credits to an API key.
    
    Note: This endpoint should be protected by admin auth in production.
    """
    if credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credits must be positive",
        )
    
    api_key = await key_service.add_credits(key_id, credits)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )
    
    return APIKeyUsage(
        key_id=api_key.key_id,
        name=api_key.name,
        tier=PricingTier(api_key.tier),
        credits_remaining=api_key.credits,
        credits_used=api_key.credits_used,
        documents_processed=api_key.documents_processed,
        pages_processed=api_key.pages_processed,
        last_used=api_key.last_used,
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate Key",
    description="Deactivate an API key.",
)
async def delete_key(
    key_id: str,
    key_service: APIKeyService = Depends(get_key_service),
):
    """
    Deactivate an API key.
    
    The key will no longer be usable for authentication.
    Note: This endpoint should be protected by admin auth in production.
    """
    success = await key_service.deactivate_key(key_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )


@router.get(
    "",
    response_model=List[APIKeyUsage],
    summary="List All Keys",
    description="List all API keys (admin only).",
)
async def list_keys(
    key_service: APIKeyService = Depends(get_key_service),
) -> List[APIKeyUsage]:
    """
    List all API keys.
    
    Note: This endpoint should be protected by admin auth in production.
    """
    keys = await key_service.list_keys()
    
    return [
        APIKeyUsage(
            key_id=k.key_id,
            name=k.name,
            tier=PricingTier(k.tier),
            credits_remaining=k.credits,
            credits_used=k.credits_used,
            documents_processed=k.documents_processed,
            pages_processed=k.pages_processed,
            last_used=k.last_used,
        )
        for k in keys
    ]
