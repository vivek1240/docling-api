"""
DocProcess Python Client SDK
============================

Async and sync clients for the DocProcess API.
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, BinaryIO
import httpx


# =============================================================================
# Exceptions
# =============================================================================

class DocProcessError(Exception):
    """Base exception for DocProcess client errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(DocProcessError):
    """Raised when API key is invalid or missing."""
    pass


class InsufficientCreditsError(DocProcessError):
    """Raised when account has insufficient credits."""
    pass


class RateLimitError(DocProcessError):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ConversionError(DocProcessError):
    """Raised when document conversion fails."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConversionResult:
    """Result of a document conversion."""
    
    source: str
    status: str
    pages: Optional[int] = None
    markdown: Optional[str] = None
    json_content: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    
    @property
    def success(self) -> bool:
        """Check if conversion was successful."""
        return self.status == "success"


@dataclass
class ConversionResponse:
    """Response from a conversion request."""
    
    request_id: str
    results: List[ConversionResult]
    credits_used: int
    credits_remaining: int
    total_processing_time_ms: int
    
    @property
    def success(self) -> bool:
        """Check if all conversions were successful."""
        return all(r.success for r in self.results)
    
    @property
    def first_result(self) -> Optional[ConversionResult]:
        """Get the first result (convenience for single document)."""
        return self.results[0] if self.results else None


@dataclass
class APIKeyInfo:
    """Information about an API key."""
    
    key_id: str
    name: str
    tier: str
    credits_remaining: int
    credits_used: int
    documents_processed: int
    pages_processed: int


# =============================================================================
# Async Client
# =============================================================================

class DocProcessClient:
    """
    Async client for the DocProcess API.
    
    Example:
        ```python
        async with DocProcessClient(api_key="your-key") as client:
            result = await client.convert_url("https://example.com/doc.pdf")
            print(result.markdown)
        ```
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        """
        Initialize the client.
        
        Args:
            api_key: Your DocProcess API key
            base_url: API base URL (default: http://localhost:8000)
            timeout: Request timeout in seconds (default: 300)
            max_retries: Maximum number of retries for failed requests (default: 3)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "DocProcessClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make an API request with error handling."""
        client = self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                response = await client.request(method, path, **kwargs)
                
                # Handle errors
                if response.status_code == 401:
                    raise AuthenticationError(
                        "Invalid or missing API key",
                        status_code=401,
                    )
                elif response.status_code == 402:
                    raise InsufficientCreditsError(
                        "Insufficient credits",
                        status_code=402,
                        details=response.json() if response.content else {},
                    )
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        "Rate limit exceeded",
                        retry_after=retry_after,
                    )
                elif response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries - 1:
                    raise DocProcessError(
                        f"HTTP error: {e.response.status_code}",
                        status_code=e.response.status_code,
                    )
            except httpx.RequestError as e:
                if attempt == self.max_retries - 1:
                    raise DocProcessError(f"Request failed: {str(e)}")
        
        raise DocProcessError("Max retries exceeded")
    
    # -------------------------------------------------------------------------
    # Document Conversion
    # -------------------------------------------------------------------------
    
    async def convert_url(
        self,
        url: str,
        output_format: str = "markdown",
    ) -> ConversionResponse:
        """
        Convert a document from URL.
        
        Args:
            url: URL of the document to convert
            output_format: Output format ('markdown', 'json', or 'both')
        
        Returns:
            ConversionResponse with results
        """
        data = await self._request(
            "POST",
            "/v1/convert/source",
            json={
                "sources": [{"kind": "http", "url": url}],
                "options": {"output_format": output_format},
            },
        )
        return self._parse_conversion_response(data)
    
    async def convert_urls(
        self,
        urls: List[str],
        output_format: str = "markdown",
    ) -> ConversionResponse:
        """
        Convert multiple documents from URLs.
        
        Args:
            urls: List of document URLs
            output_format: Output format ('markdown', 'json', or 'both')
        
        Returns:
            ConversionResponse with results for all documents
        """
        data = await self._request(
            "POST",
            "/v1/convert/source",
            json={
                "sources": [{"kind": "http", "url": url} for url in urls],
                "options": {"output_format": output_format},
            },
        )
        return self._parse_conversion_response(data)
    
    async def convert_file(
        self,
        file_path: Union[str, Path],
        output_format: str = "markdown",
    ) -> ConversionResponse:
        """
        Convert a local file.
        
        Args:
            file_path: Path to the document file
            output_format: Output format ('markdown', 'json', or 'both')
        
        Returns:
            ConversionResponse with results
        """
        path = Path(file_path)
        
        with open(path, "rb") as f:
            data = await self._request(
                "POST",
                "/v1/convert/file",
                files={"file": (path.name, f)},
                params={"output_format": output_format},
            )
        
        return self._parse_conversion_response(data)
    
    async def convert_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        output_format: str = "markdown",
    ) -> ConversionResponse:
        """
        Convert document from bytes.
        
        Args:
            file_bytes: Document file content as bytes
            filename: Original filename
            output_format: Output format ('markdown', 'json', or 'both')
        
        Returns:
            ConversionResponse with results
        """
        data = await self._request(
            "POST",
            "/v1/convert/file",
            files={"file": (filename, file_bytes)},
            params={"output_format": output_format},
        )
        return self._parse_conversion_response(data)
    
    # -------------------------------------------------------------------------
    # Async Jobs
    # -------------------------------------------------------------------------
    
    async def submit_async_job(
        self,
        urls: List[str],
    ) -> str:
        """
        Submit documents for async processing.
        
        Args:
            urls: List of document URLs
        
        Returns:
            Job ID for status polling
        """
        data = await self._request(
            "POST",
            "/v1/convert/source/async",
            json={
                "sources": [{"kind": "http", "url": url} for url in urls],
            },
        )
        return data["job_id"]
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of an async job.
        
        Args:
            job_id: The job ID
        
        Returns:
            Job status information
        """
        return await self._request("GET", f"/v1/status/{job_id}")
    
    async def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
    ) -> ConversionResponse:
        """
        Wait for an async job to complete.
        
        Args:
            job_id: The job ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None for no limit)
        
        Returns:
            ConversionResponse when job completes
        
        Raises:
            ConversionError: If job fails
            TimeoutError: If timeout exceeded
        """
        start_time = time.time()
        
        while True:
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
            
            status = await self.get_job_status(job_id)
            
            if status["status"] == "completed":
                return self._parse_conversion_response(status["result"])
            elif status["status"] == "failed":
                raise ConversionError(
                    f"Job failed: {status.get('error', 'Unknown error')}",
                )
            
            await asyncio.sleep(poll_interval)
    
    # -------------------------------------------------------------------------
    # Account
    # -------------------------------------------------------------------------
    
    async def get_account_info(self) -> APIKeyInfo:
        """
        Get information about the current API key.
        
        Returns:
            APIKeyInfo with usage statistics
        """
        data = await self._request("GET", "/v1/keys/me")
        return APIKeyInfo(
            key_id=data["key_id"],
            name=data["name"],
            tier=data["tier"],
            credits_remaining=data["credits_remaining"],
            credits_used=data["credits_used"],
            documents_processed=data["documents_processed"],
            pages_processed=data["pages_processed"],
        )
    
    async def get_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Args:
            days: Number of days to include (default: 30)
        
        Returns:
            Usage statistics dictionary
        """
        return await self._request("GET", f"/v1/usage/stats?days={days}")
    
    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check API health status.
        
        Returns:
            Health status information
        """
        # Health endpoint doesn't require auth, use bare client
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/health")
            return response.json()
    
    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    
    def _parse_conversion_response(self, data: Dict[str, Any]) -> ConversionResponse:
        """Parse API response into ConversionResponse."""
        results = [
            ConversionResult(
                source=r.get("source", "unknown"),
                status=r.get("status", "error"),
                pages=r.get("pages"),
                markdown=r.get("markdown"),
                json_content=r.get("json"),
                error=r.get("error"),
                processing_time_ms=r.get("processing_time_ms"),
            )
            for r in data.get("results", [])
        ]
        
        return ConversionResponse(
            request_id=data.get("request_id", ""),
            results=results,
            credits_used=data.get("credits_used", 0),
            credits_remaining=data.get("credits_remaining", 0),
            total_processing_time_ms=data.get("total_processing_time_ms", 0),
        )


# =============================================================================
# Sync Client Wrapper
# =============================================================================

class DocProcessClientSync:
    """
    Synchronous wrapper for DocProcessClient.
    
    Example:
        ```python
        client = DocProcessClientSync(api_key="your-key")
        result = client.convert_url("https://example.com/doc.pdf")
        print(result.markdown)
        ```
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize with same arguments as DocProcessClient."""
        self._async_client = DocProcessClient(*args, **kwargs)
    
    def _run(self, coro):
        """Run async coroutine synchronously."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    def convert_url(self, url: str, output_format: str = "markdown") -> ConversionResponse:
        """Convert document from URL (sync)."""
        return self._run(self._async_client.convert_url(url, output_format))
    
    def convert_urls(self, urls: List[str], output_format: str = "markdown") -> ConversionResponse:
        """Convert multiple documents from URLs (sync)."""
        return self._run(self._async_client.convert_urls(urls, output_format))
    
    def convert_file(self, file_path: Union[str, Path], output_format: str = "markdown") -> ConversionResponse:
        """Convert local file (sync)."""
        return self._run(self._async_client.convert_file(file_path, output_format))
    
    def get_account_info(self) -> APIKeyInfo:
        """Get account info (sync)."""
        return self._run(self._async_client.get_account_info())
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health (sync)."""
        return self._run(self._async_client.health_check())
