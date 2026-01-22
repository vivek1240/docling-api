"""
Modal Deployment for Docling Document Processing Service
=========================================================

Deploy with: modal deploy deployments/modal/modal_docling.py
Run locally: modal run deployments/modal/modal_docling.py

This provides serverless GPU-accelerated document processing with:
- Automatic scaling based on demand
- Pay-per-use pricing (only charged when processing)
- Cold start optimization with model caching
"""

import modal
from typing import Optional
import os

# =============================================================================
# Modal App Configuration
# =============================================================================

app = modal.App("docling-service")

# Base image with all dependencies
docling_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender-dev",
        "libgomp1",
        "poppler-utils",  # For PDF processing
    )
    .pip_install(
        "docling>=2.0.0",
        "docling-core>=2.0.0",
        "torch>=2.0.0",
        "easyocr>=1.7.0",
        "python-multipart>=0.0.6",
        "fastapi[standard]",  # Required for web endpoints
    )
    .env({
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
    })
)

# Volume for caching models (persists across invocations)
model_cache = modal.Volume.from_name("docling-model-cache", create_if_missing=True)


# =============================================================================
# Docling Processing Functions
# =============================================================================

@app.function(
    image=docling_image,
    gpu="T4",                    # GPU type: T4, A10G, A100
    timeout=600,                 # 10 minute max timeout
    memory=16384,                # 16GB RAM
    scaledown_window=120,        # Keep warm for 2 minutes
    volumes={"/cache": model_cache},
)
def process_document(
    file_bytes: bytes,
    filename: str,
    output_format: str = "markdown",
    enable_ocr: bool = True,
    enable_table_extraction: bool = True,
) -> dict:
    """
    Process a document and return structured output.
    
    Args:
        file_bytes: Raw bytes of the document file
        filename: Original filename (used to determine file type)
        output_format: Output format - 'markdown', 'json', or 'both'
        enable_ocr: Whether to enable OCR for scanned documents
        enable_table_extraction: Whether to extract table structures
    
    Returns:
        dict with 'markdown', 'json', or both depending on output_format
    """
    import tempfile
    import os
    from docling.document_converter import DocumentConverter
    
    # Set cache directory
    os.environ["HF_HOME"] = "/cache/huggingface"
    os.environ["TORCH_HOME"] = "/cache/torch"
    
    # Get file extension
    suffix = os.path.splitext(filename)[1].lower()
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        temp_path = f.name
    
    try:
        # Create converter
        converter = DocumentConverter()
        
        # Convert document
        result = converter.convert(temp_path)
        
        # Build response
        response = {
            "status": "success",
            "filename": filename,
            "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
        }
        
        if output_format in ("markdown", "both"):
            response["markdown"] = result.document.export_to_markdown()
        
        if output_format in ("json", "both"):
            response["json"] = result.document.export_to_dict()
        
        return response
        
    except Exception as e:
        return {
            "status": "error",
            "filename": filename,
            "error": str(e),
        }
    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=120,
    volumes={"/cache": model_cache},
)
def process_url(
    url: str,
    output_format: str = "markdown",
    enable_ocr: bool = True,
    enable_table_extraction: bool = True,
) -> dict:
    """
    Process a document from URL and return structured output.
    
    Args:
        url: URL of the document to process
        output_format: Output format - 'markdown', 'json', or 'both'
        enable_ocr: Whether to enable OCR for scanned documents
        enable_table_extraction: Whether to extract table structures
    
    Returns:
        dict with processing results
    """
    import os
    from docling.document_converter import DocumentConverter
    
    # Set cache directory
    os.environ["HF_HOME"] = "/cache/huggingface"
    os.environ["TORCH_HOME"] = "/cache/torch"
    
    try:
        # Create converter
        converter = DocumentConverter()
        
        # Convert document from URL
        result = converter.convert(url)
        
        # Build response
        response = {
            "status": "success",
            "source_url": url,
            "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
        }
        
        if output_format in ("markdown", "both"):
            response["markdown"] = result.document.export_to_markdown()
        
        if output_format in ("json", "both"):
            response["json"] = result.document.export_to_dict()
        
        return response
        
    except Exception as e:
        return {
            "status": "error",
            "source_url": url,
            "error": str(e),
        }


@app.function(
    image=docling_image,
    gpu="T4",
    timeout=1800,  # 30 minutes for batch
    memory=16384,
    scaledown_window=120,
    volumes={"/cache": model_cache},
)
def process_batch(
    documents: list[dict],
    output_format: str = "markdown",
) -> list[dict]:
    """
    Process multiple documents in batch.
    
    Args:
        documents: List of dicts with 'file_bytes' and 'filename', or 'url'
        output_format: Output format for all documents
    
    Returns:
        List of processing results
    """
    results = []
    
    for doc in documents:
        if "url" in doc:
            result = process_url.local(
                url=doc["url"],
                output_format=output_format,
            )
        elif "file_bytes" in doc and "filename" in doc:
            result = process_document.local(
                file_bytes=doc["file_bytes"],
                filename=doc["filename"],
                output_format=output_format,
            )
        else:
            result = {"status": "error", "error": "Invalid document format"}
        
        results.append(result)
    
    return results


# =============================================================================
# Web Endpoint (for direct HTTP access)
# =============================================================================

@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=120,
    volumes={"/cache": model_cache},
)
@modal.fastapi_endpoint(method="POST")
def convert_endpoint(request: dict) -> dict:
    """
    HTTP endpoint for document conversion.
    
    Request body:
        - url: URL of document to process
        - output_format: 'markdown', 'json', or 'both' (default: 'markdown')
    
    Returns:
        Processing result
    """
    url = request.get("url")
    output_format = request.get("output_format", "markdown")
    
    if not url:
        return {"status": "error", "error": "URL is required"}
    
    return process_url.local(url=url, output_format=output_format)


# =============================================================================
# CLI for Testing
# =============================================================================

@app.local_entrypoint()
def main(
    url: str = "https://arxiv.org/pdf/2501.17887",
    output_format: str = "markdown",
):
    """Test the Docling service with a sample document."""
    print(f"Processing document from: {url}")
    result = process_url.remote(url=url, output_format=output_format)
    
    if result["status"] == "success":
        print(f"\n✅ Successfully processed document ({result.get('pages', '?')} pages)")
        if "markdown" in result:
            print("\n--- Markdown Output (first 2000 chars) ---")
            print(result["markdown"][:2000])
    else:
        print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
