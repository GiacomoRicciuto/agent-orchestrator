"""
Database engine and session management.
Lazy initialization to avoid crashes at import time.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Lazy engine — created on first use, not at import time
_engine = None
_async_session = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.config import get_settings
        url = get_settings().async_database_url
        print(f"  [DB] Connecting to: {url[:30]}...{url[-20:]}")
        _engine = create_async_engine(url, echo=False, pool_size=10, max_overflow=20)
    return _engine


def _get_session_factory():
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session


async def get_db() -> AsyncSession:
    """Dependency: yields a database session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all tables."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
