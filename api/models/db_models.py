"""
Database Models
===============

SQLAlchemy ORM models for persistent storage.
"""

import secrets
import hashlib
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
    Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


def generate_key_id() -> str:
    """Generate a unique API key ID."""
    return f"dk_{secrets.token_urlsafe(8)}"


def generate_key_secret() -> str:
    """Generate a secure API key secret."""
    return secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    """Hash an API key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKey(Base):
    """
    API Key model for authentication and billing.
    
    The actual key is only shown once on creation.
    We store a hash for validation.
    """
    __tablename__ = "api_keys"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default="starter", nullable=False)
    
    # Credit balance
    credits: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Usage stats
    documents_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Stripe integration
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Relationships
    usage_records: Mapped[List["UsageRecord"]] = relationship(
        "UsageRecord", back_populates="api_key", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<APIKey {self.key_id} ({self.name})>"
    
    @classmethod
    def create_new(cls, name: str, tier: str = "starter", credits: int = 100) -> tuple["APIKey", str]:
        """
        Create a new API key.
        
        Returns:
            Tuple of (APIKey instance, full_key)
            The full_key is only available at creation time.
        """
        key_id = generate_key_id()
        key_secret = generate_key_secret()
        full_key = f"{key_id}_{key_secret}"
        
        api_key = cls(
            key_id=key_id,
            key_hash=hash_key(full_key),
            name=name,
            tier=tier,
            credits=credits,
        )
        
        return api_key, full_key
    
    def validate_key(self, full_key: str) -> bool:
        """Validate a full API key against the stored hash."""
        return self.key_hash == hash_key(full_key)
    
    def deduct_credits(self, credits: int, documents: int = 1, pages: int = 1) -> bool:
        """
        Deduct credits from this key.
        
        Returns:
            True if successful, False if insufficient credits.
        """
        if self.credits < credits:
            return False
        
        self.credits -= credits
        self.credits_used += credits
        self.documents_processed += documents
        self.pages_processed += pages
        self.last_used = datetime.utcnow()
        
        return True
    
    def add_credits(self, credits: int) -> None:
        """Add credits to this key."""
        self.credits += credits


class UsageRecord(Base):
    """
    Usage record for tracking API usage per request.
    """
    __tablename__ = "usage_records"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    
    # Request info
    request_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Processing details
    documents: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    api_key: Mapped["APIKey"] = relationship("APIKey", back_populates="usage_records")
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_usage_api_key_created", "api_key_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<UsageRecord {self.request_id} ({self.credits} credits)>"


class StripeEvent(Base):
    """
    Track processed Stripe webhook events to ensure idempotency.
    """
    __tablename__ = "stripe_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self) -> str:
        return f"<StripeEvent {self.event_id}>"
