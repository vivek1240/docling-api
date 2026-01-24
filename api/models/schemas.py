"""
Pydantic Schemas for API Request/Response Models
=================================================
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, HttpUrl


# =============================================================================
# Enums
# =============================================================================

class DocumentSourceKind(str, Enum):
    """Type of document source."""
    HTTP = "http"
    BASE64 = "base64"


class OutputFormat(str, Enum):
    """Output format for document conversion."""
    MARKDOWN = "markdown"
    JSON = "json"
    BOTH = "both"


class JobStatus(str, Enum):
    """Status of an async job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PricingTier(str, Enum):
    """Pricing tiers for API access."""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class VLMProvider(str, Enum):
    """VLM provider options."""
    GRANITE = "granite"    # Free, runs locally on Modal GPU (IBM GraniteDocling)
    OPENAI = "openai"      # Paid, uses OpenAI API (GPT-4.1-mini, etc.)


class VLMModel(str, Enum):
    """Supported VLM models for OpenAI provider."""
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1_NANO = "gpt-4.1-nano"
    O4_MINI = "o4-mini"


# =============================================================================
# API Key Models
# =============================================================================

class APIKeyCreate(BaseModel):
    """Request model for creating a new API key."""
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    tier: PricingTier = Field(default=PricingTier.STARTER, description="Pricing tier")
    credits: int = Field(default=100, ge=0, description="Initial credits")
    
    model_config = {"json_schema_extra": {"example": {"name": "My App", "tier": "starter", "credits": 100}}}


class APIKeyResponse(BaseModel):
    """Response model for API key operations."""
    id: str = Field(..., description="API key ID")
    key: str = Field(..., description="The API key (only shown once on creation)")
    name: str = Field(..., description="Name of the API key")
    tier: PricingTier = Field(..., description="Pricing tier")
    credits: int = Field(..., description="Available credits")
    created_at: datetime = Field(..., description="Creation timestamp")
    is_active: bool = Field(default=True, description="Whether the key is active")


class APIKeyUsage(BaseModel):
    """Current usage information for an API key."""
    key_id: str
    name: str
    tier: PricingTier
    credits_remaining: int
    credits_used: int
    documents_processed: int
    pages_processed: int
    last_used: Optional[datetime] = None


# =============================================================================
# Document Processing Models
# =============================================================================

class DocumentSource(BaseModel):
    """Source specification for a document."""
    kind: DocumentSourceKind = Field(..., description="Type of source")
    url: Optional[HttpUrl] = Field(None, description="URL for HTTP source")
    data: Optional[str] = Field(None, description="Base64 encoded data")
    filename: Optional[str] = Field(None, description="Original filename")
    
    model_config = {"json_schema_extra": {"example": {"kind": "http", "url": "https://arxiv.org/pdf/2501.17887"}}}


class ConversionOptions(BaseModel):
    """Options for document conversion."""
    output_format: OutputFormat = Field(default=OutputFormat.MARKDOWN, description="Output format")
    
    # OCR Options
    enable_ocr: bool = Field(default=False, description="Enable OCR to extract text from images")
    force_full_page_ocr: bool = Field(default=False, description="Force OCR on entire page (for scanned docs)")
    enable_table_extraction: bool = Field(default=True, description="Extract table structures")
    
    # VLM Options (Vision Language Model for advanced parsing)
    enable_vlm: bool = Field(default=False, description="Use Vision Language Model for advanced parsing")
    vlm_provider: str = Field(default="granite", description="VLM provider: 'granite' (free, local GPU) or 'openai' (paid, highest quality)")
    vlm_model: str = Field(default="gpt-4.1-mini", description="OpenAI model to use when vlm_provider='openai'")
    vlm_api_key: Optional[str] = Field(default=None, description="Custom OpenAI API key (optional, uses default if not provided)")


class ConversionRequest(BaseModel):
    """Request model for document conversion."""
    sources: List[DocumentSource] = Field(..., min_length=1, max_length=10)
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    
    model_config = {"json_schema_extra": {"example": {
        "sources": [{"kind": "http", "url": "https://arxiv.org/pdf/2501.17887"}],
        "options": {"output_format": "markdown"}
    }}}


class DocumentResult(BaseModel):
    """Result for a single document conversion."""
    source: str = Field(..., description="Source identifier (URL or filename)")
    status: str = Field(..., description="Processing status")
    pages: Optional[int] = Field(None, description="Number of pages processed")
    markdown: Optional[str] = Field(None, description="Markdown output")
    json_content: Optional[Dict[str, Any]] = Field(None, alias="json", description="JSON output")
    error: Optional[str] = Field(None, description="Error message if failed")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")


class ConversionResponse(BaseModel):
    """Response model for document conversion."""
    request_id: str = Field(..., description="Unique request ID")
    results: List[DocumentResult] = Field(..., description="Conversion results")
    credits_used: int = Field(..., description="Credits consumed")
    credits_remaining: int = Field(..., description="Remaining credits")
    total_processing_time_ms: int = Field(..., description="Total processing time")


# =============================================================================
# Async Job Models
# =============================================================================

class AsyncJobResponse(BaseModel):
    """Response when submitting an async job."""
    job_id: str = Field(..., description="Job ID for status polling")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current status")
    message: str = Field(default="Job submitted successfully")
    estimated_time_seconds: Optional[int] = Field(None, description="Estimated processing time")


class JobStatusResponse(BaseModel):
    """Response for job status check."""
    job_id: str
    status: JobStatus
    progress: Optional[float] = Field(None, ge=0, le=100, description="Progress percentage")
    result: Optional[ConversionResponse] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# =============================================================================
# Usage Models
# =============================================================================

class UsageRecord(BaseModel):
    """Single usage record."""
    timestamp: datetime
    request_id: str
    documents: int
    pages: int
    credits: int
    processing_time_ms: int


class UsageStats(BaseModel):
    """Usage statistics for a time period."""
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_documents: int
    total_pages: int
    total_credits: int
    average_processing_time_ms: float
    records: List[UsageRecord] = Field(default_factory=list)


# =============================================================================
# Common Models
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy")
    version: str
    docling_backend: str = Field(default="unknown")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
