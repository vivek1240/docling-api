"""
Usage and Billing Endpoints
===========================

Endpoints for viewing usage statistics and billing information.
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query

from api.auth import get_current_api_key, get_key_service
from api.services.key_service import APIKeyService
from api.models.db_models import APIKey
from api.models.schemas import UsageStats, UsageRecord, PricingTier


router = APIRouter(prefix="/v1/usage", tags=["Usage"])


# Pricing information
PRICING_TIERS = {
    PricingTier.STARTER: {
        "credits": 100,
        "price": 15.00,
        "per_document": 0.15,
        "features": ["Basic document conversion", "Email support"],
    },
    PricingTier.PROFESSIONAL: {
        "credits": 1000,
        "price": 100.00,
        "per_document": 0.10,
        "features": [
            "Priority processing",
            "OCR support",
            "Table extraction",
            "Priority support",
        ],
    },
    PricingTier.BUSINESS: {
        "credits": 5000,
        "price": 400.00,
        "per_document": 0.08,
        "features": [
            "All Professional features",
            "Batch processing",
            "Dedicated support",
            "Custom integrations",
        ],
    },
    PricingTier.ENTERPRISE: {
        "credits": None,
        "price": None,
        "per_document": None,
        "features": [
            "All Business features",
            "Custom SLA",
            "On-premise deployment",
            "24/7 support",
        ],
    },
}


@router.get(
    "/stats",
    response_model=UsageStats,
    summary="Get Usage Statistics",
    description="Get usage statistics for the current API key.",
)
async def get_usage_stats(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
    auth: tuple = Depends(get_current_api_key),
    key_service: APIKeyService = Depends(get_key_service),
) -> UsageStats:
    """
    Get usage statistics for the current API key.
    
    Returns aggregate statistics for the specified time period.
    """
    api_key, _ = auth
    
    stats = await key_service.get_usage_stats(api_key, days=days)
    
    # Convert database records to schema records
    records = [
        UsageRecord(
            timestamp=r.created_at,
            request_id=r.request_id,
            documents=r.documents,
            pages=r.pages,
            credits=r.credits,
            processing_time_ms=r.processing_time_ms,
        )
        for r in stats.get("records", [])[:100]  # Limit to 100 records
    ]
    
    return UsageStats(
        period_start=stats["period_start"],
        period_end=stats["period_end"],
        total_requests=stats["total_requests"],
        total_documents=stats["total_documents"],
        total_pages=stats["total_pages"],
        total_credits=stats["total_credits"],
        average_processing_time_ms=stats["average_processing_time_ms"],
        records=records,
    )


@router.get(
    "/pricing",
    summary="Get Pricing Information",
    description="Get current pricing tiers and features.",
)
async def get_pricing():
    """
    Get pricing information for all tiers.
    """
    return {
        "tiers": {
            tier.value: {
                "name": tier.value.title(),
                "credits": info["credits"],
                "price_usd": info["price"],
                "per_document_usd": info["per_document"],
                "features": info["features"],
            }
            for tier, info in PRICING_TIERS.items()
        },
        "notes": [
            "All prices in USD",
            "Credits do not expire",
            "Enterprise pricing available on request",
            "Volume discounts available for 50,000+ documents/month",
        ],
    }


@router.get(
    "/limits",
    summary="Get Rate Limits",
    description="Get current rate limit information.",
)
async def get_rate_limits(
    auth: tuple = Depends(get_current_api_key),
):
    """
    Get rate limit information for the current API key.
    """
    from api.config import get_settings
    
    api_key, _ = auth
    settings = get_settings()
    
    # Rate limits vary by tier
    tier_limits = {
        PricingTier.STARTER.value: 30,
        PricingTier.PROFESSIONAL.value: 60,
        PricingTier.BUSINESS.value: 120,
        PricingTier.ENTERPRISE.value: 300,
    }
    
    tier = api_key.tier
    
    return {
        "tier": tier,
        "requests_per_minute": tier_limits.get(tier, settings.rate_limit_requests_per_minute),
        "max_file_size_mb": settings.max_file_size // 1024 // 1024,
        "max_documents_per_request": 10,
        "max_pages_per_document": 500,
    }
