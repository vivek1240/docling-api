"""
Billing Endpoints
=================

Stripe integration for purchasing credits and managing subscriptions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel
from typing import Optional

from api.database import get_db
from api.auth import get_current_api_key
from api.services.stripe_service import StripeService, CREDIT_PACKAGES
from api.models.db_models import APIKey
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/v1/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    """Request for creating a checkout session."""
    package: str  # starter, professional, business
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    """Response with checkout session details."""
    checkout_url: str
    session_id: str


class PortalRequest(BaseModel):
    """Request for customer portal."""
    return_url: str


class PortalResponse(BaseModel):
    """Response with portal URL."""
    portal_url: str


async def get_stripe_service(db: AsyncSession = Depends(get_db)) -> StripeService:
    """Get Stripe service instance."""
    return StripeService(db)


@router.get(
    "/packages",
    summary="Get Available Packages",
    description="Get available credit packages for purchase.",
)
async def get_packages():
    """
    Get available credit packages.
    """
    return {
        "packages": {
            name: {
                "name": pkg["name"],
                "credits": pkg["credits"],
                "price_usd": pkg["price_cents"] / 100,
            }
            for name, pkg in CREDIT_PACKAGES.items()
        }
    }


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create Checkout Session",
    description="Create a Stripe Checkout session to purchase credits.",
)
async def create_checkout(
    body: CheckoutRequest,
    auth: tuple = Depends(get_current_api_key),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> CheckoutResponse:
    """
    Create a Stripe Checkout session for purchasing credits.
    
    Returns a URL to redirect the user to for payment.
    """
    api_key, _ = auth
    
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured. Contact support.",
        )
    
    if body.package not in CREDIT_PACKAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid package. Choose from: {list(CREDIT_PACKAGES.keys())}",
        )
    
    try:
        result = await stripe_service.create_checkout_session(
            api_key=api_key,
            package=body.package,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        
        return CheckoutResponse(
            checkout_url=result["checkout_url"],
            session_id=result["session_id"],
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}",
        )


@router.post(
    "/portal",
    response_model=PortalResponse,
    summary="Get Customer Portal",
    description="Get Stripe Customer Portal URL for managing billing.",
)
async def get_portal(
    body: PortalRequest,
    auth: tuple = Depends(get_current_api_key),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PortalResponse:
    """
    Get Stripe Customer Portal URL.
    
    Use this to let users manage their payment methods and view invoices.
    """
    api_key, _ = auth
    
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured. Contact support.",
        )
    
    if not api_key.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Make a purchase first.",
        )
    
    try:
        portal_url = await stripe_service.get_customer_portal_url(
            api_key=api_key,
            return_url=body.return_url,
        )
        
        return PortalResponse(portal_url=portal_url)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}",
        )


@router.post(
    "/webhook",
    summary="Stripe Webhook",
    description="Handle Stripe webhook events.",
    include_in_schema=False,  # Hide from docs
)
async def handle_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
    stripe_service: StripeService = Depends(get_stripe_service),
):
    """
    Handle Stripe webhook events.
    
    This endpoint receives events from Stripe for payment confirmations,
    subscription changes, etc.
    """
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured",
        )
    
    payload = await request.body()
    
    try:
        result = await stripe_service.handle_webhook(payload, stripe_signature)
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}",
        )
