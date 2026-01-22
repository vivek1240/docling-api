"""
Stripe Billing Service
======================

Handles Stripe integration for payments and credit purchases.
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.config import get_settings
from api.models.db_models import APIKey, StripeEvent
from api.services.key_service import APIKeyService


# Credit packages available for purchase
CREDIT_PACKAGES = {
    "starter": {
        "credits": 100,
        "price_cents": 1500,  # $15.00
        "name": "Starter Pack",
    },
    "professional": {
        "credits": 1000,
        "price_cents": 10000,  # $100.00
        "name": "Professional Pack",
    },
    "business": {
        "credits": 5000,
        "price_cents": 40000,  # $400.00
        "name": "Business Pack",
    },
}


class StripeService:
    """Service for handling Stripe payments and webhooks."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.key_service = APIKeyService(db)
        self._stripe = None
    
    @property
    def stripe(self):
        """Lazy-load Stripe module."""
        if self._stripe is None:
            try:
                import stripe
                settings = get_settings()
                stripe.api_key = settings.stripe_secret_key
                self._stripe = stripe
            except ImportError:
                raise RuntimeError("Stripe package not installed. Run: pip install stripe")
        return self._stripe
    
    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        settings = get_settings()
        return bool(settings.stripe_secret_key)
    
    async def create_customer(self, api_key: APIKey, email: Optional[str] = None) -> str:
        """
        Create a Stripe customer for an API key.
        
        Returns:
            Stripe customer ID
        """
        if api_key.stripe_customer_id:
            return api_key.stripe_customer_id
        
        customer = self.stripe.Customer.create(
            name=api_key.name,
            email=email,
            metadata={
                "api_key_id": api_key.key_id,
            },
        )
        
        await self.key_service.update_stripe_info(
            api_key,
            stripe_customer_id=customer.id,
        )
        
        return customer.id
    
    async def create_checkout_session(
        self,
        api_key: APIKey,
        package: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session for purchasing credits.
        
        Args:
            api_key: The API key to add credits to
            package: Package name (starter, professional, business)
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
        
        Returns:
            Dict with checkout session URL and ID
        """
        if package not in CREDIT_PACKAGES:
            raise ValueError(f"Invalid package: {package}")
        
        pkg = CREDIT_PACKAGES[package]
        
        # Ensure customer exists
        customer_id = await self.create_customer(api_key)
        
        session = self.stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": pkg["price_cents"],
                        "product_data": {
                            "name": pkg["name"],
                            "description": f"{pkg['credits']} document processing credits",
                        },
                    },
                    "quantity": 1,
                },
            ],
            metadata={
                "api_key_id": api_key.key_id,
                "package": package,
                "credits": str(pkg["credits"]),
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
    
    async def create_subscription(
        self,
        api_key: APIKey,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """
        Create a subscription checkout session.
        
        Args:
            api_key: The API key
            price_id: Stripe Price ID for the subscription
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
        
        Returns:
            Dict with checkout session URL and ID
        """
        customer_id = await self.create_customer(api_key)
        
        session = self.stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            metadata={
                "api_key_id": api_key.key_id,
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
    
    async def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Handle Stripe webhook events.
        
        Args:
            payload: Raw webhook payload
            signature: Stripe signature header
        
        Returns:
            Dict with processing result
        """
        settings = get_settings()
        
        try:
            event = self.stripe.Webhook.construct_event(
                payload,
                signature,
                settings.stripe_webhook_secret,
            )
        except ValueError:
            raise ValueError("Invalid payload")
        except self.stripe.error.SignatureVerificationError:
            raise ValueError("Invalid signature")
        
        # Check for duplicate event
        existing = await self.db.execute(
            select(StripeEvent).where(StripeEvent.event_id == event.id)
        )
        if existing.scalar_one_or_none():
            return {"status": "duplicate", "event_id": event.id}
        
        # Process event
        result = await self._process_event(event)
        
        # Record event
        stripe_event = StripeEvent(
            event_id=event.id,
            event_type=event.type,
        )
        self.db.add(stripe_event)
        await self.db.flush()
        
        return result
    
    async def _process_event(self, event) -> Dict[str, Any]:
        """Process a Stripe event."""
        event_type = event.type
        data = event.data.object
        
        if event_type == "checkout.session.completed":
            return await self._handle_checkout_completed(data)
        
        elif event_type == "invoice.paid":
            return await self._handle_invoice_paid(data)
        
        elif event_type == "customer.subscription.deleted":
            return await self._handle_subscription_deleted(data)
        
        return {"status": "ignored", "event_type": event_type}
    
    async def _handle_checkout_completed(self, session) -> Dict[str, Any]:
        """Handle successful checkout."""
        metadata = session.get("metadata", {})
        api_key_id = metadata.get("api_key_id")
        credits = int(metadata.get("credits", 0))
        
        if not api_key_id or not credits:
            return {"status": "skipped", "reason": "missing metadata"}
        
        api_key = await self.key_service.get_by_id(api_key_id)
        if not api_key:
            return {"status": "error", "reason": f"API key not found: {api_key_id}"}
        
        # Add credits
        await self.key_service.add_credits(api_key_id, credits)
        
        return {
            "status": "success",
            "action": "credits_added",
            "api_key_id": api_key_id,
            "credits": credits,
        }
    
    async def _handle_invoice_paid(self, invoice) -> Dict[str, Any]:
        """Handle paid invoice (for subscriptions)."""
        customer_id = invoice.get("customer")
        
        if not customer_id:
            return {"status": "skipped", "reason": "no customer"}
        
        api_key = await self.key_service.get_by_stripe_customer(customer_id)
        if not api_key:
            return {"status": "skipped", "reason": "customer not found"}
        
        # Determine credits based on subscription
        # This would be customized based on your subscription tiers
        subscription_id = invoice.get("subscription")
        credits_to_add = 1000  # Default for subscription
        
        await self.key_service.add_credits(api_key.key_id, credits_to_add)
        
        return {
            "status": "success",
            "action": "subscription_credits_added",
            "api_key_id": api_key.key_id,
            "credits": credits_to_add,
        }
    
    async def _handle_subscription_deleted(self, subscription) -> Dict[str, Any]:
        """Handle subscription cancellation."""
        customer_id = subscription.get("customer")
        
        if not customer_id:
            return {"status": "skipped", "reason": "no customer"}
        
        api_key = await self.key_service.get_by_stripe_customer(customer_id)
        if not api_key:
            return {"status": "skipped", "reason": "customer not found"}
        
        # Clear subscription ID
        await self.key_service.update_stripe_info(
            api_key,
            stripe_subscription_id=None,
        )
        
        return {
            "status": "success",
            "action": "subscription_cancelled",
            "api_key_id": api_key.key_id,
        }
    
    async def get_customer_portal_url(self, api_key: APIKey, return_url: str) -> str:
        """
        Get Stripe Customer Portal URL for managing billing.
        
        Args:
            api_key: The API key with Stripe customer
            return_url: URL to return to after portal
        
        Returns:
            Portal URL
        """
        if not api_key.stripe_customer_id:
            raise ValueError("No Stripe customer associated with this API key")
        
        session = self.stripe.billing_portal.Session.create(
            customer=api_key.stripe_customer_id,
            return_url=return_url,
        )
        
        return session.url
