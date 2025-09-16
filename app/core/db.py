"""Database utilities for the FastAPI application."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession, async_sessionmaker,
                                    create_async_engine)

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(settings.async_database_url, future=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a SQLAlchemy async session."""
    async with AsyncSessionLocal() as session:
        yield session
