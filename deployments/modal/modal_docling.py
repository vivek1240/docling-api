"""
Modal Deployment for Docling Document Processing Service
=========================================================

Deploy with: modal deploy deployments/modal/modal_docling.py
Run locally: modal run deployments/modal/modal_docling.py

This provides serverless GPU-accelerated document processing with:
- Automatic scaling based on demand
- Pay-per-use pricing (only charged when processing)
- Cold start optimization with model caching
- OCR support for scanned documents
- VLM support for advanced AI-powered parsing
"""

import modal
from typing import Optional
import os

# =============================================================================
# Modal App Configuration
# =============================================================================

app = modal.App("docling-service")

# Base image with all dependencies (including VLM support)
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
        "torchvision>=0.15.0",  # For VLM image processing
        "transformers>=4.40.0",  # For GraniteDocling VLM
        "accelerate>=0.30.0",  # For efficient model loading
        "easyocr>=1.7.0",
        "python-multipart>=0.0.6",
        "fastapi[standard]",  # Required for web endpoints
        "requests>=2.28.0",  # For OpenAI VLM API calls
        "python-dotenv>=1.0.0",
    )
    .env({
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "HF_HOME": "/cache/huggingface",  # Cache HuggingFace models
        "TORCH_HOME": "/cache/torch",
    })
)

# Volume for caching models (persists across invocations)
model_cache = modal.Volume.from_name("docling-model-cache", create_if_missing=True)


# =============================================================================
# Helper Functions
# =============================================================================

def create_converter(
    enable_ocr: bool = False,
    force_full_page_ocr: bool = False,
    enable_table_extraction: bool = True,
    enable_vlm: bool = False,
    vlm_provider: str = "openai",
    vlm_api_key: Optional[str] = None,
    vlm_model: str = "gpt-4.1-mini",
):
    """
    Create a DocumentConverter with the specified options.
    
    Args:
        enable_ocr: Enable OCR for text extraction from images
        force_full_page_ocr: Force OCR on entire page (for scanned docs)
        enable_table_extraction: Enable table structure extraction
        enable_vlm: Use Vision Language Model for advanced parsing
        vlm_provider: VLM provider - 'granite' (free, local) or 'openai' (paid, API)
        vlm_api_key: API key for OpenAI VLM (required if vlm_provider='openai')
        vlm_model: OpenAI model name (only used if vlm_provider='openai')
    
    Returns:
        Configured DocumentConverter instance
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
    
    # VLM takes precedence if enabled
    if enable_vlm:
        try:
            from docling.datamodel.pipeline_options import VlmPipelineOptions
            from docling.pipeline.vlm_pipeline import VlmPipeline
            
            if vlm_provider == "granite":
                # Use GraniteDocling - FREE, runs locally on GPU (experimental, slow)
                return DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_cls=VlmPipeline,
                        )
                    }
                )
            
            elif vlm_provider == "openai":
                # Use OpenAI API - requires API key
                if not vlm_api_key:
                    print("Warning: OpenAI VLM requested but no API key provided. Using standard converter.")
                    # Fall back to standard converter (NOT granite)
                    return DocumentConverter()
                
                from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
                
                pipeline_options = VlmPipelineOptions(enable_remote_services=True)
                pipeline_options.vlm_options = ApiVlmOptions(
                    url="https://api.openai.com/v1/chat/completions",
                    params=dict(model=vlm_model, max_tokens=4096),
                    headers={"Authorization": f"Bearer {vlm_api_key}"},
                    prompt="Convert this page to markdown. Extract all text, tables, and describe images.",
                    timeout=90,
                    scale=2.0,
                    response_format=ResponseFormat.MARKDOWN,
                )
                
                return DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options,
                            pipeline_cls=VlmPipeline,
                        )
                    }
                )
            
            else:
                # Unknown provider - use standard converter
                print(f"Unknown VLM provider '{vlm_provider}'. Using standard converter.")
                return DocumentConverter()
                
        except ImportError as e:
            print(f"VLM pipeline not available, falling back to standard: {e}")
    
    # OCR pipeline
    if enable_ocr:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = enable_table_extraction
        
        ocr_options = EasyOcrOptions(force_full_page_ocr=force_full_page_ocr)
        pipeline_options.ocr_options = ocr_options
        
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    
    # Standard converter (no OCR, no VLM)
    return DocumentConverter()


def process_document_with_options(
    source: str,
    output_format: str = "markdown",
    enable_ocr: bool = False,
    force_full_page_ocr: bool = False,
    enable_table_extraction: bool = True,
    enable_vlm: bool = False,
    vlm_provider: str = "openai",
    vlm_api_key: Optional[str] = None,
    vlm_model: str = "gpt-4.1-mini",
    is_url: bool = True,
    temp_path: Optional[str] = None,
) -> dict:
    """
    Process a document with the specified options.
    
    Args:
        source: URL or identifier for the document
        output_format: 'markdown', 'json', or 'both'
        enable_ocr: Enable OCR
        force_full_page_ocr: Force full page OCR
        enable_table_extraction: Enable table extraction
        enable_vlm: Enable VLM
        vlm_provider: VLM provider - 'granite' (free) or 'openai' (paid)
        vlm_api_key: VLM API key (for OpenAI)
        vlm_model: VLM model name (for OpenAI)
        is_url: Whether source is a URL (True) or file path (False)
        temp_path: Path to temp file (if processing file)
    
    Returns:
        Processing result dict
    """
    import os
    
    # Set cache directories
    os.environ["HF_HOME"] = "/cache/huggingface"
    os.environ["TORCH_HOME"] = "/cache/torch"
    
    try:
        # Create converter with options
        converter = create_converter(
            enable_ocr=enable_ocr,
            force_full_page_ocr=force_full_page_ocr,
            enable_table_extraction=enable_table_extraction,
            enable_vlm=enable_vlm,
            vlm_provider=vlm_provider,
            vlm_api_key=vlm_api_key,
            vlm_model=vlm_model,
        )
        
        # Convert document
        convert_source = source if is_url else temp_path
        result = converter.convert(convert_source)
        
        # Build response
        response = {
            "status": "success",
            "source": source,
            "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
            "ocr_enabled": enable_ocr,
            "vlm_enabled": enable_vlm,
            "vlm_provider": vlm_provider if enable_vlm else None,
        }
        
        if output_format in ("markdown", "both"):
            response["markdown"] = result.document.export_to_markdown()
        
        if output_format in ("json", "both"):
            response["json"] = result.document.export_to_dict()
        
        return response
        
    except Exception as e:
        return {
            "status": "error",
            "source": source,
            "error": str(e),
        }


# =============================================================================
# Health/Ping Endpoint (for keeping container warm)
# =============================================================================

@app.function(
    image=docling_image,
    gpu="T4",
    timeout=30,
    memory=16384,
    scaledown_window=300,  # Keep alive for 5 minutes after ping
    volumes={"/cache": model_cache},
)
@modal.fastapi_endpoint(method="GET")
def ping() -> dict:
    """
    Lightweight ping endpoint to keep the container warm.
    
    Call this every 4 minutes to prevent cold starts.
    Cost: ~$0.01 per ping (few seconds of T4 GPU time)
    
    Returns:
        Simple status response
    """
    import torch
    return {
        "status": "warm",
        "gpu_available": torch.cuda.is_available(),
        "message": "Container is ready for requests"
    }


# =============================================================================
# Web Endpoints
# =============================================================================

@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=300,  # Increased to 5 minutes
    volumes={"/cache": model_cache},
    allow_concurrent_inputs=10,
)
@modal.fastapi_endpoint(method="POST")
def convert_endpoint(request: dict) -> dict:
    """
    HTTP endpoint for document conversion from URL.
    
    Request body:
        - url: URL of document to process (required)
        - output_format: 'markdown', 'json', or 'both' (default: 'markdown')
        - enable_ocr: Enable OCR for images (default: false)
        - force_full_page_ocr: Force OCR on entire page (default: false)
        - enable_table_extraction: Enable table extraction (default: true)
        - enable_vlm: Use VLM for advanced parsing (default: false)
        - vlm_provider: 'openai' (recommended) or 'granite' (experimental) (default: 'openai')
        - vlm_api_key: API key for OpenAI VLM (optional, required if vlm_provider='openai')
        - vlm_model: OpenAI model name (default: 'gpt-4.1-mini')
    
    Returns:
        Processing result
    """
    url = request.get("url")
    if not url:
        return {"status": "error", "error": "URL is required"}
    
    return process_document_with_options(
        source=url,
        output_format=request.get("output_format", "markdown"),
        enable_ocr=request.get("enable_ocr", False),
        force_full_page_ocr=request.get("force_full_page_ocr", False),
        enable_table_extraction=request.get("enable_table_extraction", True),
        enable_vlm=request.get("enable_vlm", False),
        vlm_provider=request.get("vlm_provider", "openai"),
        vlm_api_key=request.get("vlm_api_key"),
        vlm_model=request.get("vlm_model", "gpt-4.1-mini"),
        is_url=True,
    )


@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=300,  # 5 minutes - ping every 4 min to stay warm
    volumes={"/cache": model_cache},
    allow_concurrent_inputs=10,
)
@modal.fastapi_endpoint(method="POST")
def convert_file_endpoint(request: dict) -> dict:
    """
    HTTP endpoint for file upload conversion (base64 encoded).
    
    Request body:
        - file_base64: Base64-encoded file content (required)
        - filename: Original filename (default: 'document.pdf')
        - output_format: 'markdown', 'json', or 'both' (default: 'markdown')
        - enable_ocr: Enable OCR for images (default: false)
        - force_full_page_ocr: Force OCR on entire page (default: false)
        - enable_table_extraction: Enable table extraction (default: true)
        - enable_vlm: Use VLM for advanced parsing (default: false)
        - vlm_provider: 'openai' (recommended) or 'granite' (experimental) (default: 'openai')
        - vlm_api_key: API key for OpenAI VLM (optional, required if vlm_provider='openai')
        - vlm_model: OpenAI model name (default: 'gpt-4.1-mini')
    
    Returns:
        Processing result
    """
    import base64
    import tempfile
    import os
    
    file_base64 = request.get("file_base64")
    filename = request.get("filename", "document.pdf")
    
    if not file_base64:
        return {"status": "error", "error": "file_base64 is required"}
    
    try:
        # Decode base64 file
        file_bytes = base64.b64decode(file_base64)
        
        # Get file extension
        suffix = os.path.splitext(filename)[1].lower() or ".pdf"
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(file_bytes)
            temp_path = f.name
        
        try:
            result = process_document_with_options(
                source=filename,
                output_format=request.get("output_format", "markdown"),
                enable_ocr=request.get("enable_ocr", False),
                force_full_page_ocr=request.get("force_full_page_ocr", False),
                enable_table_extraction=request.get("enable_table_extraction", True),
                enable_vlm=request.get("enable_vlm", False),
                vlm_provider=request.get("vlm_provider", "openai"),
                vlm_api_key=request.get("vlm_api_key"),
                vlm_model=request.get("vlm_model", "gpt-4.1-mini"),
                is_url=False,
                temp_path=temp_path,
            )
            return result
            
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except Exception as e:
        return {
            "status": "error",
            "filename": filename,
            "error": str(e),
        }


# =============================================================================
# Legacy Functions (for backwards compatibility)
# =============================================================================

@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=300,  # 5 minutes - ping every 4 min to stay warm
    volumes={"/cache": model_cache},
    allow_concurrent_inputs=10,
)
def process_url(
    url: str,
    output_format: str = "markdown",
    enable_ocr: bool = False,
    enable_table_extraction: bool = True,
) -> dict:
    """Process a document from URL (legacy function)."""
    return process_document_with_options(
        source=url,
        output_format=output_format,
        enable_ocr=enable_ocr,
        enable_table_extraction=enable_table_extraction,
        is_url=True,
    )


@app.function(
    image=docling_image,
    gpu="T4",
    timeout=600,
    memory=16384,
    scaledown_window=300,  # 5 minutes - ping every 4 min to stay warm
    volumes={"/cache": model_cache},
    allow_concurrent_inputs=10,
)
def process_document(
    file_bytes: bytes,
    filename: str,
    output_format: str = "markdown",
    enable_ocr: bool = False,
    enable_table_extraction: bool = True,
) -> dict:
    """Process a document from bytes (legacy function)."""
    import tempfile
    import os
    
    suffix = os.path.splitext(filename)[1].lower()
    
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        temp_path = f.name
    
    try:
        return process_document_with_options(
            source=filename,
            output_format=output_format,
            enable_ocr=enable_ocr,
            enable_table_extraction=enable_table_extraction,
            is_url=False,
            temp_path=temp_path,
        )
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# =============================================================================
# CLI for Testing
# =============================================================================

@app.local_entrypoint()
def main(
    url: str = "https://arxiv.org/pdf/2501.17887",
    output_format: str = "markdown",
    enable_ocr: bool = False,
    enable_vlm: bool = False,
):
    """Test the Docling service with a sample document."""
    print(f"Processing document from: {url}")
    print(f"Options: OCR={enable_ocr}, VLM={enable_vlm}")
    
    result = process_url.remote(
        url=url, 
        output_format=output_format,
        enable_ocr=enable_ocr,
    )
    
    if result["status"] == "success":
        print(f"\n✅ Successfully processed document ({result.get('pages', '?')} pages)")
        print(f"   OCR enabled: {result.get('ocr_enabled', False)}")
        print(f"   VLM enabled: {result.get('vlm_enabled', False)}")
        if "markdown" in result:
            print("\n--- Markdown Output (first 2000 chars) ---")
            print(result["markdown"][:2000])
    else:
        print(f"\n❌ Error: {result.get('error', 'Unknown error')}")
