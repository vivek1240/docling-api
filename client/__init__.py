"""
DocProcess Python Client SDK
============================

A Python client for interacting with the DocProcess API.

Usage:
    from client import DocProcessClient
    
    client = DocProcessClient(api_key="your-api-key")
    result = await client.convert_url("https://example.com/document.pdf")
    print(result.markdown)
"""

from client.docling_client import (
    DocProcessClient,
    DocProcessError,
    AuthenticationError,
    InsufficientCreditsError,
    RateLimitError,
    ConversionResult,
)

__all__ = [
    "DocProcessClient",
    "DocProcessError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ConversionResult",
]

__version__ = "1.0.0"
