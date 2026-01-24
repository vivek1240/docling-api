"""
Docling Backend Client
======================

Async client for communicating with the Docling backend service.
Supports both local Docker deployment and Modal cloud deployment.
"""

import asyncio
import base64
import time
from typing import Any, Dict, List, Optional, BinaryIO
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from api.config import get_settings
from api.models.schemas import DocumentSource, ConversionOptions, OutputFormat


class DoclingClient:
    """
    Async client for the Docling backend service.
    
    Provides methods for document conversion via URL or file upload,
    with automatic retries and timeout handling.
    
    Supports two backends:
    - Local/Docker: Direct HTTP calls to docling-serve
    - Modal: Serverless GPU processing via Modal endpoint
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        modal_endpoint: Optional[str] = None,
        use_modal: Optional[bool] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize the Docling client.
        
        Args:
            base_url: Docling backend URL (defaults to settings)
            modal_endpoint: Modal endpoint URL (defaults to settings)
            use_modal: Use Modal instead of local backend (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
        """
        settings = get_settings()
        self.base_url = (base_url or settings.docling_backend_url).rstrip("/")
        self.modal_endpoint = modal_endpoint or settings.docling_modal_endpoint
        self.use_modal = use_modal if use_modal is not None else settings.docling_use_modal
        self.timeout = timeout or settings.docling_timeout
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the Docling backend.
        
        Returns:
            Health status from the backend
        """
        if self.use_modal and self.modal_endpoint:
            # Modal doesn't have a health endpoint, just return OK
            return {"status": "healthy", "backend": "modal"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return {"status": "healthy", "backend": response.json()}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def convert_from_url(
        self,
        url: str,
        options: Optional[ConversionOptions] = None,
    ) -> Dict[str, Any]:
        """
        Convert a document from URL.
        
        Args:
            url: URL of the document to convert
            options: Conversion options
        
        Returns:
            Conversion result with markdown/json content
        """
        options = options or ConversionOptions()
        start_time = time.time()
        
        # Use Modal if configured
        if self.use_modal and self.modal_endpoint:
            return await self._convert_via_modal(url, options, start_time)
        
        # Use local Docker backend
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "sources": [{"kind": "http", "url": str(url)}],
            }
            
            response = await client.post(
                f"{self.base_url}/v1/convert/source",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return self._format_result(result, str(url), options, processing_time)
    
    async def _convert_via_modal(
        self,
        url: str,
        options: ConversionOptions,
        start_time: float,
    ) -> Dict[str, Any]:
        """Convert document using Modal endpoint."""
        settings = get_settings()
        output_format = options.output_format.value if options.output_format else "markdown"
        
        # Determine VLM API key (user's key or default)
        vlm_api_key = options.vlm_api_key or settings.default_vlm_api_key
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.modal_endpoint,
                json={
                    "url": url,
                    "output_format": output_format,
                    # OCR options
                    "enable_ocr": options.enable_ocr,
                    "force_full_page_ocr": options.force_full_page_ocr,
                    "enable_table_extraction": options.enable_table_extraction,
                    # VLM options
                    "enable_vlm": options.enable_vlm,
                    "vlm_api_key": vlm_api_key,
                    "vlm_model": options.vlm_model.value if hasattr(options.vlm_model, 'value') else options.vlm_model,
                },
            )
            response.raise_for_status()
            result = response.json()
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Modal returns slightly different format
            return {
                "source": url,
                "status": result.get("status", "success"),
                "pages": result.get("pages", 1),
                "markdown": result.get("markdown"),
                "json": result.get("json"),
                "processing_time_ms": processing_time,
            }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def convert_from_file(
        self,
        file: BinaryIO,
        filename: str,
        options: Optional[ConversionOptions] = None,
    ) -> Dict[str, Any]:
        """
        Convert a document from file upload.
        
        Args:
            file: File-like object with document data
            filename: Original filename
            options: Conversion options
        
        Returns:
            Conversion result with markdown/json content
        """
        options = options or ConversionOptions()
        start_time = time.time()
        
        # Use Modal if configured
        if self.use_modal and self.modal_endpoint:
            return await self._convert_file_via_modal(file, filename, options, start_time)
        
        # Use local Docker backend
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Docling expects 'files' (plural) as the field name
            files = {"files": (filename, file)}
            
            response = await client.post(
                f"{self.base_url}/v1/convert/file",
                files=files,
            )
            response.raise_for_status()
            result = response.json()
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return self._format_result(result, filename, options, processing_time)
    
    async def _convert_file_via_modal(
        self,
        file: BinaryIO,
        filename: str,
        options: ConversionOptions,
        start_time: float,
    ) -> Dict[str, Any]:
        """Convert file using Modal endpoint by base64 encoding."""
        settings = get_settings()
        output_format = options.output_format.value if options.output_format else "markdown"
        
        # Determine VLM API key (user's key or default)
        vlm_api_key = options.vlm_api_key or settings.default_vlm_api_key
        
        # Read file and encode as base64
        file_bytes = file.read()
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        
        # Send as JSON with base64 data and all options
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.modal_endpoint.replace("/convert_endpoint", "/convert_file_endpoint"),
                json={
                    "file_base64": file_base64,
                    "filename": filename,
                    "output_format": output_format,
                    # OCR options
                    "enable_ocr": options.enable_ocr,
                    "force_full_page_ocr": options.force_full_page_ocr,
                    "enable_table_extraction": options.enable_table_extraction,
                    # VLM options
                    "enable_vlm": options.enable_vlm,
                    "vlm_api_key": vlm_api_key,
                    "vlm_model": options.vlm_model.value if hasattr(options.vlm_model, 'value') else options.vlm_model,
                },
            )
            response.raise_for_status()
            result = response.json()
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return {
                "source": filename,
                "status": result.get("status", "success"),
                "pages": result.get("pages", 1),
                "markdown": result.get("markdown"),
                "json": result.get("json"),
                "processing_time_ms": processing_time,
            }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def convert_from_base64(
        self,
        data: str,
        filename: str,
        options: Optional[ConversionOptions] = None,
    ) -> Dict[str, Any]:
        """
        Convert a document from base64-encoded data.
        
        Args:
            data: Base64-encoded document data
            filename: Original filename
            options: Conversion options
        
        Returns:
            Conversion result with markdown/json content
        """
        options = options or ConversionOptions()
        start_time = time.time()
        
        # Decode base64 and send as file
        file_bytes = base64.b64decode(data)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Docling expects 'files' (plural) as the field name
            files = {"files": (filename, file_bytes)}
            
            response = await client.post(
                f"{self.base_url}/v1/convert/file",
                files=files,
            )
            response.raise_for_status()
            result = response.json()
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return self._format_result(result, filename, options, processing_time)
    
    async def convert_sources(
        self,
        sources: List[DocumentSource],
        options: Optional[ConversionOptions] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convert multiple document sources.
        
        Args:
            sources: List of document sources
            options: Conversion options
        
        Returns:
            List of conversion results
        """
        options = options or ConversionOptions()
        results = []
        
        for source in sources:
            try:
                if source.kind.value == "http" and source.url:
                    result = await self.convert_from_url(str(source.url), options)
                elif source.kind.value == "base64" and source.data:
                    filename = source.filename or "document.pdf"
                    result = await self.convert_from_base64(source.data, filename, options)
                else:
                    result = {
                        "source": source.url or source.filename or "unknown",
                        "status": "error",
                        "error": "Invalid source configuration",
                    }
                results.append(result)
            except Exception as e:
                results.append({
                    "source": str(source.url or source.filename or "unknown"),
                    "status": "error",
                    "error": str(e),
                })
        
        return results
    
    async def submit_async_job(
        self,
        sources: List[DocumentSource],
    ) -> Dict[str, Any]:
        """
        Submit an async conversion job.
        
        Args:
            sources: List of document sources
        
        Returns:
            Job submission response with job_id
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "sources": [
                    {"kind": s.kind.value, "url": str(s.url) if s.url else None}
                    for s in sources
                ],
            }
            
            response = await client.post(
                f"{self.base_url}/v1/convert/source/async",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of an async job.
        
        Args:
            job_id: The job ID to check
        
        Returns:
            Job status response
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/v1/status/{job_id}")
            response.raise_for_status()
            return response.json()
    
    def _format_result(
        self,
        raw_result: Dict[str, Any],
        source: str,
        options: ConversionOptions,
        processing_time: int,
    ) -> Dict[str, Any]:
        """Format the raw Docling response into our schema."""
        # Extract document data from various response formats
        document = raw_result.get("document", raw_result)
        
        result = {
            "source": source,
            "status": "success",
            "processing_time_ms": processing_time,
        }
        
        # Get page count
        if "pages" in document:
            result["pages"] = len(document["pages"]) if isinstance(document["pages"], list) else document["pages"]
        elif "page_count" in document:
            result["pages"] = document["page_count"]
        else:
            result["pages"] = 1
        
        # Add content based on requested format
        if options.output_format in (OutputFormat.MARKDOWN, OutputFormat.BOTH):
            result["markdown"] = document.get("md_content") or document.get("markdown") or ""
        
        if options.output_format in (OutputFormat.JSON, OutputFormat.BOTH):
            result["json"] = document
        
        return result


# Singleton client instance
_client: Optional[DoclingClient] = None


def get_docling_client() -> DoclingClient:
    """Get or create the Docling client singleton."""
    global _client
    if _client is None:
        _client = DoclingClient()
    return _client
