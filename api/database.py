"""
Database Configuration
======================

SQLAlchemy database setup with async support.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from api.config import get_settings


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Engine and session factory (initialized lazily)
_engine = None
_async_session_factory = None


def get_database_url() -> str:
    """Get the database URL, converting to async driver if needed."""
    settings = get_settings()
    url = settings.database_url
    
    # Convert sync URLs to async
    if url.startswith("sqlite:///"):
        # SQLite: sqlite:/// -> sqlite+aiosqlite:///
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif url.startswith("postgresql://"):
        # PostgreSQL: postgresql:// -> postgresql+asyncpg://
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


def get_engine():
    """Get or create the database engine."""
    global _engine
    
    if _engine is None:
        url = get_database_url()
        
        # SQLite-specific settings
        if "sqlite" in url:
            _engine = create_async_engine(
                url,
                echo=get_settings().api_debug,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,  # Wait up to 30s for locks
                },
                pool_size=1,  # SQLite works best with single connection
                max_overflow=0,
            )
            
            # Enable WAL mode for better concurrency
            @event.listens_for(_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
        else:
            _engine = create_async_engine(
                url,
                echo=get_settings().api_debug,
                pool_size=5,
                max_overflow=10,
            )
    
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
        # Import models to register them with Base
        from api.models import db_models  # noqa
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    global _engine, _async_session_factory
    
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
