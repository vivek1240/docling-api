"""
API Key Service
===============

Business logic for API key management with database persistence.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.db_models import APIKey, UsageRecord, hash_key


class APIKeyService:
    """Service for managing API keys."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_key(
        self,
        name: str,
        tier: str = "starter",
        credits: int = 100,
        stripe_customer_id: Optional[str] = None,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key.
        
        Returns:
            Tuple of (APIKey, full_key)
            The full_key is only available at creation.
        """
        api_key, full_key = APIKey.create_new(name=name, tier=tier, credits=credits)
        
        if stripe_customer_id:
            api_key.stripe_customer_id = stripe_customer_id
        
        self.db.add(api_key)
        await self.db.flush()
        
        return api_key, full_key
    
    async def get_by_id(self, key_id: str) -> Optional[APIKey]:
        """Get an API key by its key_id."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.key_id == key_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_full_key(self, full_key: str) -> Optional[APIKey]:
        """Get and validate an API key by its full key."""
        key_hash = hash_key(full_key)
        
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def validate_key(self, full_key: str) -> Optional[APIKey]:
        """
        Validate an API key and return it if valid.
        Also updates last_used timestamp.
        """
        api_key = await self.get_by_full_key(full_key)
        
        if api_key:
            api_key.last_used = datetime.utcnow()
            await self.db.flush()
        
        return api_key
    
    async def deduct_credits(
        self,
        api_key: APIKey,
        credits: int,
        documents: int = 1,
        pages: int = 1,
        request_id: str = "",
        endpoint: str = "",
        processing_time_ms: int = 0,
    ) -> bool:
        """
        Deduct credits and record usage.
        
        Returns:
            True if successful, False if insufficient credits.
        """
        if not api_key.deduct_credits(credits, documents, pages):
            return False
        
        # Record usage
        usage = UsageRecord(
            api_key_id=api_key.id,
            request_id=request_id,
            endpoint=endpoint,
            documents=documents,
            pages=pages,
            credits=credits,
            processing_time_ms=processing_time_ms,
            status="success",
        )
        self.db.add(usage)
        await self.db.flush()
        
        return True
    
    async def add_credits(self, key_id: str, credits: int) -> Optional[APIKey]:
        """Add credits to an API key."""
        api_key = await self.get_by_id(key_id)
        
        if api_key:
            api_key.add_credits(credits)
            await self.db.flush()
        
        return api_key
    
    async def deactivate_key(self, key_id: str) -> bool:
        """Deactivate an API key."""
        api_key = await self.get_by_id(key_id)
        
        if api_key:
            api_key.is_active = False
            await self.db.flush()
            return True
        
        return False
    
    async def list_keys(self, include_inactive: bool = False) -> List[APIKey]:
        """List all API keys."""
        query = select(APIKey)
        
        if not include_inactive:
            query = query.where(APIKey.is_active == True)
        
        result = await self.db.execute(query.order_by(APIKey.created_at.desc()))
        return list(result.scalars().all())
    
    async def get_usage_stats(
        self,
        api_key: APIKey,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get usage statistics for an API key."""
        since = datetime.utcnow() - timedelta(days=days)
        
        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.api_key_id == api_key.id,
                    UsageRecord.created_at >= since,
                )
            )
            .order_by(UsageRecord.created_at.desc())
        )
        records = list(result.scalars().all())
        
        total_documents = sum(r.documents for r in records)
        total_pages = sum(r.pages for r in records)
        total_credits = sum(r.credits for r in records)
        total_time = sum(r.processing_time_ms for r in records)
        
        return {
            "period_start": since,
            "period_end": datetime.utcnow(),
            "total_requests": len(records),
            "total_documents": total_documents,
            "total_pages": total_pages,
            "total_credits": total_credits,
            "average_processing_time_ms": total_time / len(records) if records else 0,
            "records": records,
        }
    
    async def get_by_stripe_customer(self, stripe_customer_id: str) -> Optional[APIKey]:
        """Get an API key by Stripe customer ID."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.stripe_customer_id == stripe_customer_id)
        )
        return result.scalar_one_or_none()
    
    async def update_stripe_info(
        self,
        api_key: APIKey,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
    ) -> None:
        """Update Stripe-related fields."""
        if stripe_customer_id is not None:
            api_key.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id is not None:
            api_key.stripe_subscription_id = stripe_subscription_id
        await self.db.flush()
