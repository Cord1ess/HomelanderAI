"""Database connection engine and session management.

Provides the async session factory and the FastAPI dependency `get_db()`.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: open a connection per request, close it after.
#
# Pooling would save a few milliseconds of connect time on a path that already
# spends seconds in model inference, and it costs two real problems here:
#
#   1. A pooled asyncpg connection belongs to the event loop that opened it.
#      Anything that runs more than one loop in a process — the test suite does,
#      one per TestClient — hands the next caller a connection tied to a closed
#      loop, which surfaces as a 500 with an asyncio traceback rather than
#      anything a person could diagnose.
#   2. The database lives on a different machine (docs/DEMO_SETUP.md). Every
#      pooled connection dies when that machine sleeps or drops off the network,
#      and the pool hands them out anyway until each one fails once.
#
# Neither is worth a few milliseconds at this scale.
engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    future=True,
    poolclass=NullPool,
    # asyncpg's own connect timeout. See settings.db_connect_timeout_seconds —
    # this is what turns a 21-second hang into a 5-second error.
    connect_args={"timeout": settings.db_connect_timeout_seconds},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one async session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
