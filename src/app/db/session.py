from collections.abc import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import Settings


def _ensure_async_driver(url: str) -> str:
    """Add +asyncpg driver if missing (handles Railway's postgresql:// format)."""
    if url.startswith("postgresql://") and "+" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Infrastructure:
    def __init__(self, settings: Settings) -> None:
        database_url = _ensure_async_driver(settings.database_url)
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()

