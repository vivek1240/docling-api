"""
Document Processing Endpoints
=============================

Core document conversion endpoints with database-backed credit tracking.
"""

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Request

from api.auth import get_current_api_key, get_key_service
from api.config import get_settings
from api.rate_limit import limiter, get_rate_limit_string
from api.services.key_service import APIKeyService
from api.models.db_models import APIKey
from api.models.schemas import (
    ConversionRequest,
    ConversionResponse,
    ConversionOptions,
    DocumentResult,
    AsyncJobResponse,
    JobStatusResponse,
    JobStatus,
    OutputFormat,
)
from api.services.docling_client import get_docling_client


router = APIRouter(prefix="/v1", tags=["Documents"])


def _calculate_credits(pages: int) -> int:
    """Calculate credits based on page count."""
    settings = get_settings()
    return max(
        pages * settings.credits_per_page,
        settings.min_credits_per_document,
    )


@router.post(
    "/convert/source",
    response_model=ConversionResponse,
    summary="Convert Document from Source",
    description="Convert one or more documents from URL or base64 data.",
)
@limiter.limit(get_rate_limit_string())
async def convert_from_source(
    request: Request,
    body: ConversionRequest,
    auth: tuple = Depends(get_current_api_key),
    key_service: APIKeyService = Depends(get_key_service),
) -> ConversionResponse:
    """
    Convert documents from URL or base64 sources.
    
    Supports:
    - HTTP URLs pointing to PDF, DOCX, or other supported formats
    - Base64-encoded document data
    
    Returns structured markdown and/or JSON output.
    """
    api_key, raw_key = auth
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    client = get_docling_client()
    
    # Process all sources
    results = await client.convert_sources(body.sources, body.options)
    
    # Calculate total pages and credits
    total_pages = sum(r.get("pages", 1) for r in results if r.get("status") == "success")
    total_credits = _calculate_credits(total_pages)
    total_documents = len([r for r in results if r.get("status") == "success"])
    
    # Check if we have enough credits
    if api_key.credits < total_credits:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {total_credits}, Available: {api_key.credits}",
        )
    
    total_time = int((time.time() - start_time) * 1000)
    
    # Deduct credits using service (persisted to database)
    success = await key_service.deduct_credits(
        api_key=api_key,
        credits=total_credits,
        documents=total_documents,
        pages=total_pages,
        request_id=request_id,
        endpoint="/v1/convert/source",
        processing_time_ms=total_time,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Failed to deduct credits",
        )
    
    # Format results
    document_results = [
        DocumentResult(
            source=r.get("source", "unknown"),
            status=r.get("status", "error"),
            pages=r.get("pages"),
            markdown=r.get("markdown"),
            json=r.get("json"),
            error=r.get("error"),
            processing_time_ms=r.get("processing_time_ms"),
        )
        for r in results
    ]
    
    return ConversionResponse(
        request_id=request_id,
        results=document_results,
        credits_used=total_credits,
        credits_remaining=api_key.credits,  # Already deducted
        total_processing_time_ms=total_time,
    )


@router.post(
    "/convert/file",
    response_model=ConversionResponse,
    summary="Convert Uploaded File",
    description="Convert an uploaded document file.",
)
@limiter.limit(get_rate_limit_string())
async def convert_from_file(
    request: Request,
    file: UploadFile = File(..., description="Document file to convert"),
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    enable_ocr: bool = False,
    force_full_page_ocr: bool = False,
    enable_vlm: bool = False,
    vlm_provider: str = "granite",
    vlm_api_key: Optional[str] = None,
    vlm_model: str = "gpt-4.1-mini",
    auth: tuple = Depends(get_current_api_key),
    key_service: APIKeyService = Depends(get_key_service),
) -> ConversionResponse:
    """
    Convert an uploaded document file.
    
    Supports PDF, DOCX, PPTX, HTML, and image files.
    Maximum file size is configured by the server (default 100MB).
    
    Options:
    - enable_ocr: Enable OCR to extract text from images
    - force_full_page_ocr: Force OCR on entire page (for scanned docs)
    - enable_vlm: Use Vision Language Model for advanced parsing
    - vlm_provider: 'granite' (free, local GPU) or 'openai' (paid, highest quality)
    - vlm_api_key: Custom OpenAI API key (optional, uses default if not provided)
    - vlm_model: OpenAI model to use (gpt-4.1-mini, gpt-5-mini, etc.)
    """
    api_key, raw_key = auth
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    settings = get_settings()
    
    # Check file size
    file_content = await file.read()
    if len(file_content) > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.max_file_size // 1024 // 1024}MB",
        )
    
    # Reset file position for reading
    await file.seek(0)
    
    client = get_docling_client()
    options = ConversionOptions(
        output_format=output_format,
        enable_ocr=enable_ocr,
        force_full_page_ocr=force_full_page_ocr,
        enable_vlm=enable_vlm,
        vlm_provider=vlm_provider,
        vlm_api_key=vlm_api_key,
        vlm_model=vlm_model,
    )
    
    try:
        result = await client.convert_from_file(file.file, file.filename or "document", options)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document conversion failed: {str(e)}",
        )
    
    # Calculate credits
    pages = result.get("pages", 1)
    credits = _calculate_credits(pages)
    
    if api_key.credits < credits:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {credits}, Available: {api_key.credits}",
        )
    
    total_time = int((time.time() - start_time) * 1000)
    
    # Deduct credits
    success = await key_service.deduct_credits(
        api_key=api_key,
        credits=credits,
        documents=1,
        pages=pages,
        request_id=request_id,
        endpoint="/v1/convert/file",
        processing_time_ms=total_time,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Failed to deduct credits",
        )
    
    return ConversionResponse(
        request_id=request_id,
        results=[
            DocumentResult(
                source=file.filename or "uploaded_file",
                status=result.get("status", "success"),
                pages=pages,
                markdown=result.get("markdown"),
                json=result.get("json"),
                processing_time_ms=result.get("processing_time_ms"),
            )
        ],
        credits_used=credits,
        credits_remaining=api_key.credits,
        total_processing_time_ms=total_time,
    )


@router.post(
    "/convert/source/async",
    response_model=AsyncJobResponse,
    summary="Submit Async Conversion Job",
    description="Submit a document for asynchronous processing.",
)
@limiter.limit(get_rate_limit_string())
async def submit_async_conversion(
    request: Request,
    body: ConversionRequest,
    auth: tuple = Depends(get_current_api_key),
) -> AsyncJobResponse:
    """
    Submit documents for asynchronous processing.
    
    Returns a job ID that can be used to poll for status.
    Use this for large documents or when you don't want to wait for completion.
    """
    api_key, raw_key = auth
    
    # Check minimum credits
    min_credits = len(body.sources) * get_settings().min_credits_per_document
    if api_key.credits < min_credits:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Minimum required: {min_credits}",
        )
    
    client = get_docling_client()
    
    try:
        result = await client.submit_async_job(body.sources)
        job_id = result.get("job_id", str(uuid.uuid4()))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit job: {str(e)}",
        )
    
    return AsyncJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Job submitted successfully",
        estimated_time_seconds=30 * len(body.sources),
    )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get Job Status",
    description="Check the status of an async conversion job.",
)
async def get_job_status(
    job_id: str,
    auth: tuple = Depends(get_current_api_key),
) -> JobStatusResponse:
    """
    Get the status of an async conversion job.
    
    Poll this endpoint until status is 'completed' or 'failed'.
    """
    from datetime import datetime
    
    client = get_docling_client()
    
    try:
        result = await client.get_job_status(job_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    status_str = result.get("status", "pending").lower()
    
    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus(status_str) if status_str in [s.value for s in JobStatus] else JobStatus.PENDING,
        progress=result.get("progress"),
        result=result.get("result"),
        error=result.get("error"),
        created_at=result.get("created_at", datetime.utcnow()),
        completed_at=result.get("completed_at"),
    )
