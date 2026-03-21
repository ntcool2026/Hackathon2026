"""Database engine, session factory, and dependency injection for SQLAlchemy async."""
from collections.abc import AsyncGenerator

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.settings import settings

# Only require SSL for non-local connections (Railway/production uses SSL; local Postgres doesn't)
_local_hosts = ("@localhost", "@127.0.0.1", "@0.0.0.0")
_use_ssl = not any(h in settings.database_url for h in _local_hosts)
_connect_args = {"ssl": "require"} if _use_ssl else {}

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=300,       # recycle every 5 min — Railway proxy drops idle connections
    pool_pre_ping=True,     # test connection before use, discard if dead
    echo=False,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
