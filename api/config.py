"""
Configuration Management
========================

Centralized configuration using Pydantic Settings with environment variable support.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # -------------------------------------------------------------------------
    # API Service Configuration
    # -------------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_debug: bool = Field(default=False, description="Debug mode")
    api_title: str = Field(default="DocProcess API", description="API title")
    api_version: str = Field(default="1.0.0", description="API version")
    api_secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for signing tokens",
    )
    
    # -------------------------------------------------------------------------
    # Docling Backend Configuration
    # -------------------------------------------------------------------------
    docling_backend_url: str = Field(
        default="http://localhost:5001",
        description="URL of the Docling backend service (local Docker or self-hosted)",
    )
    docling_modal_endpoint: Optional[str] = Field(
        default=None,
        description="Modal endpoint URL for cloud GPU processing (overrides docling_backend_url)",
    )
    docling_use_modal: bool = Field(
        default=False,
        description="Use Modal for document processing instead of local backend",
    )
    docling_timeout: int = Field(
        default=300,
        description="Timeout for document processing (seconds)",
    )
    max_file_size: int = Field(
        default=104857600,  # 100MB
        description="Maximum file size in bytes",
    )
    
    # -------------------------------------------------------------------------
    # VLM (Vision Language Model) Configuration
    # -------------------------------------------------------------------------
    default_vlm_api_key: Optional[str] = Field(
        default=None,
        description="Default OpenAI API key for VLM (used when user doesn't provide one)",
    )
    default_vlm_model: str = Field(
        default="gpt-4.1-mini",
        description="Default VLM model to use",
    )
    vlm_api_base_url: str = Field(
        default="https://api.openai.com/v1/chat/completions",
        description="Base URL for VLM API",
    )
    
    # -------------------------------------------------------------------------
    # Database Configuration
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="sqlite:///./docprocess.db",
        description="Database connection URL",
    )
    
    # -------------------------------------------------------------------------
    # Redis Configuration
    # -------------------------------------------------------------------------
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL for rate limiting",
    )
    
    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting",
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Maximum requests per minute per API key",
    )
    rate_limit_burst: int = Field(
        default=10,
        description="Burst allowance for rate limiting",
    )
    
    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format")
    
    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS",
    )
    
    # -------------------------------------------------------------------------
    # Pricing Tiers (credits per document based on pages)
    # -------------------------------------------------------------------------
    credits_per_page: int = Field(
        default=1,
        description="Credits consumed per page processed",
    )
    min_credits_per_document: int = Field(
        default=1,
        description="Minimum credits per document",
    )
    
    # -------------------------------------------------------------------------
    # Stripe Configuration
    # -------------------------------------------------------------------------
    stripe_secret_key: Optional[str] = Field(
        default=None,
        description="Stripe secret key for payments",
    )
    stripe_webhook_secret: Optional[str] = Field(
        default=None,
        description="Stripe webhook signing secret",
    )
    stripe_price_id_starter: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for starter subscription",
    )
    stripe_price_id_professional: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for professional subscription",
    )
    stripe_price_id_business: Optional[str] = Field(
        default=None,
        description="Stripe Price ID for business subscription",
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
