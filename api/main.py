"""
DocProcess API - Main Application
==================================

FastAPI application that wraps Docling for commercial document processing.
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api import __version__
from api.config import get_settings
from api.rate_limit import limiter
from api.database import init_db, close_db
from api.routes import health_router, documents_router, keys_router, usage_router, billing_router


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings = get_settings()
    
    # Startup
    logger.info(
        "Starting DocProcess API",
        version=__version__,
        debug=settings.api_debug,
        docling_backend=settings.docling_backend_url,
    )
    
    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down DocProcess API")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="""
## DocProcess API

A commercial document processing service powered by [Docling](https://github.com/docling-project/docling).

### Features

- **Multi-format Support**: PDF, DOCX, PPTX, HTML, and images
- **AI-Powered Extraction**: Layout analysis, table extraction, and OCR
- **Structured Output**: Export to Markdown or JSON
- **Credit-Based Pricing**: Pay only for what you use
- **Persistent Storage**: API keys and usage data stored in database

### Authentication

All endpoints (except health checks) require API key authentication.

Include your API key in the `Authorization` header:

```
Authorization: Bearer YOUR_API_KEY
```

### Rate Limits

- Starter: 30 requests/minute
- Professional: 60 requests/minute
- Business: 120 requests/minute
- Enterprise: 300 requests/minute

### Support

For questions or issues, contact support@yourdomain.com
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time
        import uuid
        
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Add request ID to state for access in routes
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Request completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            error=str(exc),
            path=request.url.path,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    
    # Include routers
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(keys_router)
    app.include_router(usage_router)
    app.include_router(billing_router)
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
    )
