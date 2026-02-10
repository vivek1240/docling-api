"""
Database Configuration
======================

SQLAlchemy database setup with async support.
Supports both SQLite (dev) and PostgreSQL (production).
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from api.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Engine and session factory (initialized lazily)
_engine = None
_async_session_factory = None


def _mask_url(url: str) -> str:
    """Mask password in URL for safe logging."""
    try:
        if "://" in url and "@" in url:
            pre = url.split("://")[0] + "://"
            rest = url.split("://", 1)[1]
            if ":" in rest and "@" in rest:
                user = rest.split(":")[0]
                after_at = rest.split("@", 1)[1]
                return f"{pre}{user}:****@{after_at}"
        return url[:30] + "..." if len(url) > 30 else url
    except Exception:
        return "***masked***"


def get_database_url() -> str:
    """
    Get the database URL, converting to async driver if needed.

    Handles:
    - sqlite:///         -> sqlite+aiosqlite:///
    - postgresql://      -> postgresql+asyncpg://
    - postgres://        -> postgresql+asyncpg://  (Railway shorthand)
    """
    settings = get_settings()
    url = settings.database_url

    # Log the raw URL (masked password) for debugging
    logger.info(f"Raw DATABASE_URL: {_mask_url(url)}")

    # Railway sometimes provides postgres:// instead of postgresql://
    if url.startswith("postgres://") and not url.startswith("postgresql://"):
        url = "postgresql://" + url[len("postgres://"):]
        logger.info("Converted postgres:// to postgresql://")

    # Convert sync URLs to async drivers
    if url.startswith("sqlite:///"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        logger.error(
            f"Unrecognized DATABASE_URL scheme: {_mask_url(url)}. "
            "Expected postgresql:// or sqlite:///. "
            "Check your DATABASE_URL environment variable."
        )
        raise ValueError(
            f"Invalid DATABASE_URL scheme. Got: {_mask_url(url)}. "
            "Expected: postgresql://... or sqlite:///..."
        )

    logger.info(f"Using async database URL: {_mask_url(url)}")
    return url


def get_engine():
    """Get or create the database engine."""
    global _engine

    if _engine is None:
        url = get_database_url()

        if "sqlite" in url:
            _engine = create_async_engine(
                url,
                echo=get_settings().api_debug,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
            )
            logger.info("Created SQLite async engine")
        else:
            _engine = create_async_engine(
                url,
                echo=get_settings().api_debug,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=300,
            )
            logger.info("Created PostgreSQL async engine (pool_size=5, max_overflow=10)")

    return _engine


def get_session_factory():
    """Get or create the async session factory."""
    global _async_session_factory

    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _async_session_factory


async def get_db() -> AsyncSession:
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialize database tables."""
    engine = get_engine()

    async with engine.begin() as conn:
        from api.models import db_models  # noqa
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialized successfully")


async def close_db():
    """Close database connections."""
    global _engine, _async_session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")
